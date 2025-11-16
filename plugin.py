"""
<plugin key="LyrionMusicServer" name="Lyrion Music Server" author="MadPatrick" version="1.6.2" wikilink="https://lyrion.org" externallink="https://github.com/MadPatrick/domoticz_LMS">
    <description>
        <h2>Lyrion Music Server Plugin - Extended</h2>
        <p>Version 1.6.2</p>
        <p>Detects players, creates devices, and provides:</p>
        <ul>
            <li>Power / Play / Pause / Stop</li>
            <li>Volume (Dimmer)</li>
            <li>Track info (Text)</li>
            <li>Playlists (Selector)</li>
            <li>Sync / Unsync</li>
            <li>Display text (via Actions device)</li>
            <li>Shuffle (Selector)</li>
            <li>Repeat (Selector)</li>
        </ul>
    </description>

    <params>
        <param field="Address" label="Server IP" width="200px" required="true" default="192.168.1.6"/>
        <param field="Port" label="Port" width="100px" required="true" default="9000"/>
        <param field="Username" label="Username" width="150px"/>
        <param field="Password" label="Password" width="150px" password="true"/>
        <param field="Mode1" label="Polling interval (sec)" width="100px" default="10"/>
        <param field="Mode2" label="Max playlists to expose" width="100px" default="10"/>
        <param field="Mode3" label="Debug logging" width="100px" default="No">
            <options>
                <option label="No" value="False"/>
                <option label="Yes" value="True"/>
            </options>
        </param>
        <param field="Mode4" label="Message text" width="300px" default="Hello from Domoticz!" />
    </params>

</plugin>
"""

import Domoticz
import requests
import time

PLAYLISTS_DEVICE_UNIT = 250


class LMSPlugin:
    def __init__(self):

        self.url = ""
        self.auth = None
        self.pollInterval = 30
        self.nextPoll = 0
        self.players = []
        self.playlists = []
        self.max_playlists = 50
        self.imageID = 0
        self.debug = False

        # Display text settings
        self.displayText = ""          # Mode4: line2
        self.subjectText = "Lyrion"    # line1
        self.displayDuration = 60

        # Logging and initialization tracking
        self.initialized = False
        self.createdDevices = 0
        self.activePlaylist = None

        # Track-change detection
        self.lastTrackIndex = {}

    def onStart(self):
        Domoticz.Log("Lyrion plugin started (v1.6.2).")

        _IMAGE = "lyrion"

        if _IMAGE not in Images:
            Domoticz.Log(f"Lyrion icons not found, loading {_IMAGE}.zip ...")
            Domoticz.Image(f"{_IMAGE}.zip").Create()

        if _IMAGE in Images:
            self.imageID = Images[_IMAGE].ID
            Domoticz.Log(f"Lyrion icons loaded (ImageID={self.imageID})")
        else:
            Domoticz.Error(f"Unable to load Lyrion icon pack '{_IMAGE}.zip'!")

        self.pollInterval = int(Parameters.get("Mode1", 30))
        self.max_playlists = int(Parameters.get("Mode2", 50))
        self.debug = Parameters.get("Mode3", "False").lower() == "true"

        self.displayText = Parameters.get("Mode4", "")
        Domoticz.Log(f"Display text (line2) = '{self.displayText}'")

        self.url = f"http://{Parameters['Address']}:{Parameters['Port']}/jsonrpc.js"

        user = Parameters.get("Username", "")
        pwd  = Parameters.get("Password", "")
        self.auth = (user, pwd) if user else None

        Domoticz.Heartbeat(10)
        self.nextPoll = time.time() + 10

    def onStop(self):
        Domoticz.Log("Lyrion plugin stopped.")

    def onHeartbeat(self):
        if time.time() >= self.nextPoll:
            self.nextPoll = time.time() + self.pollInterval
            self.updateEverything()

    #
    # JSON WRAPPER
    #
    def lms_query_raw(self, player, cmd_array):
        data = {"id": 1, "method": "slim.request", "params": [player, cmd_array]}
        try:
            r = requests.post(self.url, json=data, auth=self.auth, timeout=10)
            r.raise_for_status()
            return r.json().get("result")
            if self.debug:
                Domoticz.Log(f"DEBUG Query: player={player}, cmd={cmd_array}, result={result}")
        except Exception as e:
            Domoticz.Error(f"LMS query error: {e}")
            return None

    def get_serverstatus(self):
        return self.lms_query_raw("", ["serverstatus", 0, 999])

    def get_status(self, playerid):
        return self.lms_query_raw(playerid, ["status", "-", 1, "tags:adclmntyK"])

    def get_playlists(self):
        return self.lms_query_raw("", ["playlists", 0, 999])

    def send_playercmd(self, playerid, cmd_array):
        return self.lms_query_raw(playerid, cmd_array)

    def send_button(self, playerid, button):
        return self.send_playercmd(playerid, ["button", button])


    #
    # DISPLAY TEXT
    #
    def send_display_text(self, playerid, line2_text):
        if not playerid or not line2_text:
            return

        line1 = self.subjectText[:64].replace('"', "'")
        line2 = line2_text[:128].replace('"', "'")
        d = self.displayDuration

        cmd = [
            "show",
            f"line1:{line1}",
            f"line2:{line2}",
            f"duration:{d}",
            "brightness:4",
            "font:huge"
        ]

        self.send_playercmd(playerid, cmd)

    #
    # DEVICE CREATION
    #
    def create_player_devices(self, name, mac):

        base = name
        unit = 1
        while unit in Devices:
            unit += 10

        opts_main = {
            "LevelNames": "Off|Pause|Play|Stop",
            "LevelActions": "||||",
            "SelectorStyle": "0"
        }

        Domoticz.Device(
            Name=base,
            Unit=unit,
            TypeName="Selector Switch",
            Switchtype=18,
            Options=opts_main,
            Image=self.imageID,
            Description=mac,
            Used=1
        ).Create()

        Domoticz.Device(
            Name=f"{base} Volume",
            Unit=unit+1,
            Type=244,
            Subtype=73,
            Switchtype=7,
            Image=5,
            Description=mac,
            Used=1
        ).Create()

        Domoticz.Device(
            Name=f"{base} Track",
            Unit=unit+2,
            TypeName="Text",
            Image=self.imageID,
            Description=mac,
            Used=1
        ).Create()

        opts_act = {
            "LevelNames": "None|SendText|Sync to this|Unsync",
            "LevelActions": "||",
            "SelectorStyle": "0"
        }

        Domoticz.Device(
            Name=f"{base} Actions",
            Unit=unit+3,
            TypeName="Selector Switch",
            Switchtype=18,
            Options=opts_act,
            Image=self.imageID,
            Description=mac,
            Used=1
        ).Create()

        opts_shuffle = {
            "LevelNames": "Off|Songs|Albums",
            "LevelActions": "||",
            "SelectorStyle": "0"
        }

        Domoticz.Device(
            Name=f"{base} Shuffle",
            Unit=unit+4,
            TypeName="Selector Switch",
            Switchtype=18,
            Options=opts_shuffle,
            Image=self.imageID,
            Description=mac,
            Used=1
        ).Create()

        opts_repeat = {
            "LevelNames": "Off|Track|Playlist",
            "LevelActions": "||",
            "SelectorStyle": "0"
        }

        Domoticz.Device(
            Name=f"{base} Repeat",
            Unit=unit+5,
            TypeName="Selector Switch",
            Switchtype=18,
            Options=opts_repeat,
            Image=self.imageID,
            Description=mac,
            Used=1
        ).Create()

        self.createdDevices += 6
        return (unit, unit+1, unit+2, unit+3, unit+4, unit+5)

    def find_player_devices(self, mac):

        main = vol = text = actions = shuffle = repeat = None

        for uid, dev in Devices.items():
            if dev.Description != mac:
                continue

            if dev.Name.endswith("Volume"):
                vol = uid
            elif dev.Name.endswith("Track"):
                text = uid
            elif dev.Name.endswith("Actions"):
                actions = uid
            elif dev.Name.endswith("Shuffle"):
                shuffle = uid
            elif dev.Name.endswith("Repeat"):
                repeat = uid
            else:
                main = uid

        if main:
            return (main, vol, text, actions, shuffle, repeat)
        return None

    #
    # PLAYLIST MANAGEMENT
    #
    def reload_playlists(self):

        root = self.get_playlists()
        if not root:
            self.playlists = []
        else:
            pl = root.get("playlists_loop", [])
            self.playlists = [{
                "id": p.get("id"),
                "playlist": p.get("playlist", ""),
                "refid": int(p.get("id", 0)) % 256
            } for p in pl[:self.max_playlists]]

        if not self.playlists:
            levelnames = "Select|No playlists"
        else:
            levelnames = "Select|" + "|".join(p["playlist"] for p in self.playlists)

        opts = {
            "LevelNames": levelnames,
            "LevelActions": "",
            "SelectorStyle": "1"
        }

        if PLAYLISTS_DEVICE_UNIT not in Devices:
            Domoticz.Device(
                Name="Lyrion Playlists",
                Unit=PLAYLISTS_DEVICE_UNIT,
                TypeName="Selector Switch",
                Switchtype=18,
                Options=opts,
                Image=self.imageID,
                Used=1
            ).Create()
        else:
            dev = Devices[PLAYLISTS_DEVICE_UNIT]
            if dev.Options.get("LevelNames", "") != levelnames:
                dev.Update(nValue=0, sValue=dev.sValue, Options=opts)

    #
    # PLAYLIST STARTER
    #
    def play_playlist_by_level(self, Level):

        if Level < 10:
            return

        idx = int(Level // 10) - 1

        if idx < 0 or idx >= len(self.playlists):
            Domoticz.Error("Invalid playlist index.")
            return

        playlist_name = self.playlists[idx]["playlist"]
        self.activePlaylist = playlist_name

        self.start_playlist_on_first_player(playlist_name)

        selected_level = (idx + 1) * 10
        if PLAYLISTS_DEVICE_UNIT in Devices:
            Devices[PLAYLISTS_DEVICE_UNIT].Update(
                nValue=0, sValue=str(selected_level)
            )

    def start_playlist_on_first_player(self, playlist_name):

        if not self.players:
            return

        first = self.players[0]
        mac = first.get("playerid")

        self.send_playercmd(mac, ["playlist", "clear"])
        self.send_playercmd(mac, ["playlist", "load", playlist_name])
        self.send_playercmd(mac, ["play"])

        self.nextPoll = time.time() + 1

    #
    # MAIN UPDATE LOOP
    #
    def updateEverything(self):

        server = self.get_serverstatus()
        if not server:
            Domoticz.Error("Lyrion server not responding.")
            return

        self.players = server.get("players_loop", [])

        # Ensure devices exist for each player
        for p in self.players:
            name = p.get("name", "Unknown")
            mac  = p.get("playerid", "")
            if mac and not self.find_player_devices(mac):
                self.create_player_devices(name, mac)

        self.reload_playlists()

        #
        # PROCESS EACH PLAYER
        #
        for p in self.players:

            mac  = p.get("playerid")
            if not mac:
                continue

            devices = self.find_player_devices(mac)
            if not devices:
                continue

            main, vol, text, actions, shuffle, repeat = devices
            st = self.get_status(mac) or {}

            power = int(st.get("power", 0))
            mode  = st.get("mode", "stop")

            sel_level = {"pause": 10, "play": 20, "stop": 30}.get(mode, 0)
            if power == 0:
                sel_level = 0

            #
            # MAIN PLAYER STATE
            #
            if main in Devices:
                dev_main = Devices[main]
                n = 1 if power else 0
                s = str(sel_level)
                if dev_main.nValue != n or dev_main.sValue != s:
                    dev_main.Update(nValue=n, sValue=s)

            #
            # VOLUME
            #
            if vol in Devices:
                dev_vol = Devices[vol]
                old = int(dev_vol.sValue) if dev_vol.sValue.isdigit() else 0
                try:
                    new = int(str(st.get("mixer volume")))
                except:
                    new = old
                if new != old:
                    dev_vol.Update(nValue=1 if new > 0 else 0, sValue=str(new))

            #
            # TRACK — *** FIXED METADATA HANDLING ***
            #
            if text in Devices:
                dev_text = Devices[text]

                remote = st.get("remote", 0)
                rm = st.get("remoteMeta", {})
                pl = st.get("playlist_loop", [])

                title = ""
                artist = ""

                # 1) remoteMeta — BEST source for radio streams
                if remote and rm:
                    title = rm.get("title", "") or title
                    artist = rm.get("artist", "") or artist

                # 2) playlist_loop fallback (also works for streams)
                if not title and isinstance(pl, list) and pl:
                    title = pl[0].get("title", "") or title
                    artist = pl[0].get("artist", "") or artist

                # 3) fallback: station name (current_title)
                if not title:
                    title = st.get("current_title", "")

                # Build the display label
                if not title:
                    label = " "
                elif artist:
                    label = f"{artist} - {title}"
                else:
                    label = title

                label = label[:255]

                #
                # TRACK CHANGE DETECTION
                #
                track_index = st.get("playlist_cur_index")
                player_key = mac
                changed = False

                if track_index is not None:
                    if (
                        player_key not in self.lastTrackIndex
                        or self.lastTrackIndex[player_key] != track_index
                    ):
                        changed = True
                        self.lastTrackIndex[player_key] = track_index

                #
                # Update device if text OR track changed
                #
                if dev_text.sValue != label or changed:
                    dev_text.Update(nValue=0, sValue=label)

            #
            # SHUFFLE
            #
            if shuffle in Devices:
                dev_shuffle = Devices[shuffle]
                try:
                    shuffle_state = int(st.get("playlist shuffle", 0))
                except:
                    shuffle_state = 0
                level = shuffle_state * 10
                if dev_shuffle.sValue != str(level):
                    dev_shuffle.Update(nValue=0, sValue=str(level))

            #
            # REPEAT
            #
            if repeat in Devices:
                dev_repeat = Devices[repeat]
                try:
                    repeat_state = int(st.get("playlist repeat", 0))
                except:
                    repeat_state = 0
                level = repeat_state * 10
                if dev_repeat.sValue != str(level):
                    dev_repeat.Update(nValue=0, sValue=str(level))

        #
        # INITIALIZATION LOG
        #
        if not self.initialized:
            Domoticz.Log("Lyrion initialized:")
            Domoticz.Log(f" Players       : {len(self.players)}")
            Domoticz.Log(f" Devices       : {self.createdDevices}")
            Domoticz.Log(f" Playlists     : {len(self.playlists)}")
            Domoticz.Log(f" Poll interval : {self.pollInterval} sec")
            self.initialized = True

    #
    # COMMAND HANDLER
    #
    def onCommand(self, Unit, Command, Level, Hue):

        if Unit not in Devices:
            return

        dev = Devices[Unit]
        devname = dev.Name
        mac = dev.Description

        if self.debug:
            Domoticz.Log(
                f"DEBUG onCommand: Unit={Unit}, Name={devname}, "
                f"Command={Command}, Level={Level}, mac={mac}"
            )


        # Playlist selector
        if Unit == PLAYLISTS_DEVICE_UNIT and Command == "Set Level":
            self.play_playlist_by_level(Level)
            return

        # Actions selector
        if "Actions" in devname and Command == "Set Level":

            if Level == 10:
                if not self.displayText:
                    Domoticz.Error("Message text (Mode4) is empty.")
                    return
                self.send_display_text(mac, self.displayText)
                dev.Update(nValue=1, sValue=str(Level))
                return

            if Level == 20:
                self.send_playercmd(mac, ["sync", mac])
                dev.Update(nValue=1, sValue=str(Level))
                Domoticz.Log(f"Sync to this: {devname} ({mac})")
                return

            if Level == 30:
                self.send_playercmd(mac, ["sync", "-"])
                dev.Update(nValue=1, sValue=str(Level))
                Domoticz.Log(f"Unsync: {devname} ({mac})")
                return

        # Shuffle
        if "Shuffle" in devname:
            if Command == "Set Level":
                mode = int(Level // 10)
            else:
                mode = 0
            self.send_playercmd(mac, ["playlist", "shuffle", str(mode)])
            dev.Update(nValue=0, sValue=str(Level))
            if "Shuffle" in devname:
                if Command == "Set Level":
                    mode = int(Level // 10)
                else:
                    mode = 0

                self.send_playercmd(mac, ["playlist", "shuffle", str(mode)])
                dev.Update(nValue=0, sValue=str(Level))

                # Tekstuele mapping voor log
                shuffle_text = {0: "Off", 1: "Songs", 2: "Albums"}.get(mode, f"Unknown ({mode})")
                Domoticz.Log(f"Lyrion: Shuffle set to: {shuffle_text}")
                return

        # Repeat
        if "Repeat" in devname:
            if Command == "Set Level":
                mode = int(Level // 10)
            else:
                mode = 0
            self.send_playercmd(mac, ["playlist", "repeat", str(mode)])
            dev.Update(nValue=0, sValue=str(Level))
            if "Repeat" in devname:
                if Command == "Set Level":
                    mode = int(Level // 10)
                else:
                    mode = 0

            # Stuur command
            self.send_playercmd(mac, ["playlist", "repeat", str(mode)])
            dev.Update(nValue=0, sValue=str(Level))

            # MAPPING van cijfers naar tekst
            repeat_text = {0: "Off", 1: "Track", 2: "Playlist"}.get(mode, f"Unknown ({mode})")

            Domoticz.Log(f"Lyrion: Repeat set to: {repeat_text}")
            return

        # Power
        if Command in ["On", "Off"] and not any(
            x in devname for x in ("Volume", "Track", "Actions", "Shuffle", "Repeat")
        ):
            self.send_playercmd(mac, ["power", "1" if Command == "On" else "0"])
            dev.Update(nValue=1 if Command == "On" else 0, sValue="")
            Domoticz.Log(f"Power {Command}")
            return

        # Volume
        if "Volume" in devname and Command == "Set Level":
            self.send_playercmd(mac, ["mixer", "volume", str(Level)])
            dev.Update(nValue=1 if Level > 0 else 0, sValue=str(Level))
            Domoticz.Log(f"Volume set to {Level}%") 
            return

        # Play / Pause / Stop
        if Command == "Set Level":
            btn = {10: "pause.single", 20: "play.single", 30: "stop"}.get(Level)
            if btn:
                self.send_button(mac, btn)
                dev.Update(nValue=1, sValue=str(Level))
                Domoticz.Log(f"Command '{btn_cmd}'")
                return


#
# DOMOTICZ HOOKS
#
_plugin = LMSPlugin()

def onStart():
    _plugin.onStart()

def onStop():
    _plugin.onStop()

def onHeartbeat():
    _plugin.onHeartbeat()

def onCommand(Unit, Command, Level, Hue):
    _plugin.onCommand(Unit, Command, Level, Hue)

