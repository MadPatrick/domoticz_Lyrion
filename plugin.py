"""
<plugin key="LogitechMediaServer" name="Logitech Media Server (extended)" author="You" version="1.2.1" wikilink="https://github.com/Logitech/slimserver" externallink="https://mysqueezebox.com">
    <description>
        <h2>Logitech Media Server Plugin - Extended</h2>
        Detecteert spelers, maakt devices aan en biedt:
        - Power / Play / Pause / Stop
        - Volume (Dimmer)
        - Track info (Text)
        - Playlists (Selector)
        - Sync / Unsync
        - Display text (via Actions device)
    </description>
    <params>
        <param field="Address" label="Server IP" width="200px" required="true" default="127.0.0.1"/>
        <param field="Port" label="Port" width="100px" required="true" default="9000"/>
        <param field="Username" label="Username" width="150px"/>
        <param field="Password" label="Password" width="150px" password="true"/>
        <param field="Mode1" label="Polling interval (sec)" width="100px" default="30"/>
        <param field="Mode2" label="Max playlists to expose" width="100px" default="50"/>
    </params>
</plugin>
"""

import Domoticz
import requests
import time

PLAYLISTS_DEVICE_UNIT = 250  # vaste unit, binnen Domoticz-bereik


class LMSPlugin:
    def __init__(self):
        self.url = ""
        self.auth = None
        self.pollInterval = 30
        self.nextPoll = 0
        self.players = []
        self.playlists = []
        self.max_playlists = 50

    # -------------------------
    # Core plugin lifecycle
    # -------------------------
    def onStart(self):
        Domoticz.Log("LMS Plugin started.")
        self.pollInterval = int(Parameters.get("Mode1", 30))
        self.max_playlists = int(Parameters.get("Mode2", 50))
        self.url = f"http://{Parameters.get('Address', '127.0.0.1')}:{Parameters.get('Port', '9000')}/jsonrpc.js"
        username = Parameters.get("Username", "")
        password = Parameters.get("Password", "")
        self.auth = (username, password) if username else None
        Domoticz.Heartbeat(10)

        # Wacht één heartbeat voordat apparaten worden aangemaakt
        self.nextPoll = time.time() + 10
        Domoticz.Log("LMS Plugin initialization delayed until first heartbeat.")

    def onStop(self):
        Domoticz.Log("LMS Plugin stopped.")

    def onHeartbeat(self):
        if time.time() >= self.nextPoll:
            self.nextPoll = time.time() + self.pollInterval
            self.updateEverything()

    # -------------------------
    # LMS JSON-RPC helpers
    # -------------------------
    def lms_query_raw(self, player, cmd_array):
        data = {"id": 1, "method": "slim.request", "params": [player, cmd_array]}
        try:
            r = requests.post(self.url, json=data, auth=self.auth, timeout=6)
            r.raise_for_status()
            j = r.json()
            return j.get("result", j)
        except Exception as e:
            Domoticz.Error(f"LMS query error: {e}")
            return None

    def get_serverstatus(self):
        return self.lms_query_raw("", ["serverstatus", 0, 999])

    def get_status(self, playerid, tags="tags:acdegklmnrtu"):
        return self.lms_query_raw(playerid, ["status", "-", 1, tags])

    def get_playlists(self):
        return self.lms_query_raw("", ["playlists", 0, 999])

    def send_playercmd(self, playerid, cmd_array):
        return self.lms_query_raw(playerid, cmd_array)

    def send_button(self, playerid, button):
        return self.send_playercmd(playerid, ["button", button])

    def send_display_text(self, playerid, subject, text, duration=5):
        if not playerid or not text:
            return
        s1 = str(subject)[:64].replace('"', "'")
        s2 = str(text)[:128].replace('"', "'")
        cmd = ["show", f"line1:{s1}", f"line2:{s2}", f"duration:{duration}", "brightness:4", "font:huge"]
        self.send_playercmd(playerid, cmd)
        Domoticz.Log(f"Display text sent to {playerid}: {s1} / {s2}")

    # -------------------------
    # Device helpers
    # -------------------------
    def friendly_dev_name(self, name, mac):
        return f"{name} [{mac}]"

    def find_player_devices(self, mac):
        for u, dev in Devices.items():
            if dev.Name.endswith(f"[{mac}]"):
                baseprefix = dev.Name[:-(len(mac) + 3)]
                main = vol = text = actions = None
                for uid, d in Devices.items():
                    if d.Name.startswith(baseprefix) and d.Name.endswith(f"[{mac}]"):
                        if "Volume" in d.Name:
                            vol = uid
                        elif "Track" in d.Name:
                            text = uid
                        elif "Actions" in d.Name:
                            actions = uid
                        else:
                            main = uid
                return (main, vol, text, actions)
        return None

    def create_player_devices(self, name, mac):
        friendly = self.friendly_dev_name(name, mac)
        main_unit = None
        for u, dev in Devices.items():
            if dev.Name == friendly:
                main_unit = u
                break

        if main_unit is None:
            unit = 1
            while unit in Devices:
                unit += 10  # stap van 10 per speler
            options = {"LevelNames": "Off|Pause|Play|Stop", "LevelActions": "||||", "SelectorStyle": "0"}
            Domoticz.Device(Name=friendly, Unit=unit, TypeName="Selector Switch", Switchtype=18, Options=options).Create()
            Domoticz.Log(f"Created main device {friendly} unit {unit}")
            main_unit = unit

        # Gebruik kleine offsets binnen bereik
        vol_unit = main_unit + 1
        text_unit = main_unit + 2
        actions_unit = main_unit + 3

        if vol_unit not in Devices:
            Domoticz.Device(Name=f"{name} Volume [{mac}]", Unit=vol_unit, TypeName="Dimmer").Create()
            Domoticz.Log(f"Created volume device unit {vol_unit}")

        if text_unit not in Devices:
            Domoticz.Device(Name=f"{name} Track [{mac}]", Unit=text_unit, TypeName="Text").Create()
            Domoticz.Log(f"Created track info device unit {text_unit}")

        if actions_unit not in Devices:
            opts = {"LevelNames": "None|SendText|Sync to this|Unsync", "LevelActions": "||", "SelectorStyle": "0"}
            Domoticz.Device(Name=f"{name} Actions [{mac}]", Unit=actions_unit, TypeName="Selector Switch", Switchtype=18, Options=opts).Create()
            Domoticz.Log(f"Created actions device unit {actions_unit}")

        return (main_unit, vol_unit, text_unit, actions_unit)

    # -------------------------
    # Updating players & playlists
    # -------------------------
    def reload_playlists(self):
        root = self.get_playlists()
        if not root:
            self.playlists = []
            return

        pl = root.get("playlists_loop", [])
        self.playlists = [{"id": p.get("id"), "playlist": p.get("playlist", ""), "refid": int(p.get("id", 0)) % 256} for p in pl[:self.max_playlists]]

        if PLAYLISTS_DEVICE_UNIT not in Devices:
            levelnames = "|".join([p["playlist"] for p in self.playlists]) if self.playlists else "No playlists"
            opts = {"LevelNames": levelnames, "LevelActions": "||", "SelectorStyle": "0"}
            Domoticz.Device(Name="LMS Playlists", Unit=PLAYLISTS_DEVICE_UNIT, TypeName="Selector Switch", Switchtype=18, Options=opts).Create()
            Domoticz.Log(f"Created Playlists device unit {PLAYLISTS_DEVICE_UNIT}")
            return  # voorkomt Device_init fout tijdens eerste aanmaak

    def updateEverything(self):
        server = self.get_serverstatus()
        if not server:
            Domoticz.Error(f"No response from LMS server at {self.url}")
            return

        self.players = server.get("players_loop", [])

        for p in self.players:
            name, mac = p.get("name", "Unknown"), p.get("playerid", "")
            if not mac:
                continue
            devices = self.find_player_devices(mac)
            if not devices:
                self.create_player_devices(name, mac)

        self.reload_playlists()

        for p in self.players:
            name, mac = p.get("name", "Unknown"), p.get("playerid", "")
            if not mac:
                continue
            devices = self.find_player_devices(mac)
            if not devices:
                continue
            main, vol, text, actions = devices

            st = self.get_status(mac) or {}
            power = int(st.get("power", 0))
            mode = st.get("mode", "stop")
            mixer_vol = int(st.get("mixer volume", 0))
            sel_level = {"pause": 10, "play": 20, "stop": 30}.get(mode, 0)

            if main in Devices:
                nval = 1 if power == 1 else 0
                sval = str(sel_level)
                if Devices[main].nValue != nval or Devices[main].sValue != sval:
                    Devices[main].Update(nValue=nval, sValue=sval)

            if vol in Devices:
                onoff = 1 if mixer_vol > 0 else 0
                sval = str(mixer_vol)
                if Devices[vol].nValue != onoff or Devices[vol].sValue != sval:
                    Devices[vol].Update(nValue=onoff, sValue=sval)

            if text in Devices:
                title, artist, album, year = st.get("title", ""), st.get("artist", ""), st.get("album", ""), st.get("year", "")
                label = title or "(empty playlist)"
                if artist:
                    label += f" - {artist}"
                if year and year != "0":
                    label += f" ({year})"
                label = label[:255]
                if Devices[text].sValue != label:
                    Devices[text].Update(nValue=0, sValue=label)

    # -------------------------
    # Handling commands from Domoticz UI
    # -------------------------
    def onCommand(self, Unit, Command, Level, Hue):
        Domoticz.Log(f"onCommand Unit={Unit} Command={Command} Level={Level}")

        if Unit == PLAYLISTS_DEVICE_UNIT and Command == "Set Level" and self.playlists:
            idx = int(Level) - 1
            if 0 <= idx < len(self.playlists):
                target_mac = self.players[0].get("playerid") if self.players else None
                if target_mac:
                    pl = self.playlists[idx]
                    self.send_playercmd(target_mac, ["playlist", "play", pl["playlist"]])
                    self.updateEverything()
            return

        # Player actions device (main_unit + 3)
        if Unit % 10 == 4:
            main_unit = Unit - 3
            if main_unit in Devices:
                devname = Devices[main_unit].Name
                mac = devname.split("[")[-1].strip("]") if "[" in devname else None
                if not mac:
                    return
                if Command == "Set Level":
                    if Level == 1:
                        self.send_display_text(mac, "Domoticz", "Message from Domoticz")
                    elif Level == 2:
                        [self.send_playercmd(mac, ["sync", p["playerid"]]) for p in self.players if p.get("playerid") != mac]
                    elif Level == 3:
                        self.send_playercmd(mac, ["sync", "-"])
                Devices[Unit].Update(nValue=0, sValue="0")
            return

        # Player main or volume controls
        if Unit in Devices:
            devname = Devices[Unit].Name
            mac = devname.split("[")[-1].strip("]") if "[" in devname else None
            if not mac:
                return

            if Command == "On":
                self.send_playercmd(mac, ["power", "1"])
            elif Command == "Off":
                self.send_playercmd(mac, ["power", "0"])
            elif Command == "Set Level":
                if "Volume" in devname:
                    self.send_playercmd(mac, ["mixer", "volume", str(Level)])
                else:
                    self.send_button(mac, {10: "pause.single", 20: "play.single", 30: "stop"}.get(Level, "stop"))
            self.updateEverything()


# --- Plugin instance ---
_plugin = LMSPlugin()


def onStart():
    _plugin.onStart()


def onStop():
    _plugin.onStop()


def onHeartbeat():
    _plugin.onHeartbeat()


def onCommand(Unit, Command, Level, Hue):
    _plugin.onCommand(Unit, Command, Level, Hue)
