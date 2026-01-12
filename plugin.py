"""
<plugin key="LyrionMusicServer" name="Lyrion Music Server" author="MadPatrick" version="2.0.9" wikilink="https://lyrion.org" externallink="https://github.com/MadPatrick/domoticz_Lyrion">
    <description>
        <h2><br/>Lyrion Music Server Plugin</h2>
        <p>Version 2.0.9</p>
        <p>Detects players, creates devices, and provides:</p>
        <ul>
            <li>Power / Play / Pause / Stop</li>
            <li>Volume (Dimmer)</li>
            <li>Track info (Text)</li>
            <li>Playlists (Selector) - per player (player-specific list)</li>
            <li>Sync / Unsync</li>
            <li>Display text (via Actions device)</li>
            <li>Shuffle (Selector)</li>
            <li>Repeat (Selector)</li>
        </ul>
        <br/><span style="font-weight: bold;">Lyrion Server settings</span>
    </description>
    <params>
        <param field="Address" label="Server IP" width="200px" required="true" default="192.168.1.6"/>
        <param field="Port" label="Port" width="100px" required="true" default="9000"/>
        <param field="Username" label="Username" width="150px">
            <description>
                <br/><span style="color: yellow;">Login settings. Only needed when applicable</span>
            </description>
        </param>
        <param field="Password" label="Password" width="150px" password="true">
        </param>
        <param field="Mode1" label="Polling interval (sec)" width="100px" default="10">
            <description>
                <br/>
            </description>
            <options>
                <option label="20 sec" value="20"/>
                <option label="5 sec" value="5"/>
                <option label="10 sec" value="10" default="10"/>
                <option label="30 sec" value="30"/>
                <option label="60 sec" value="60"/>
            </options>
        </param>
        <param field="Mode2" label="Max playlists to load" width="100px" default="5"/>
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

class LMSPlugin:
    def __init__(self):
        self.url = ""
        self.auth = None
        self.pollInterval = 30
        self.nextPoll = 0
        self.players = []

        # per-player playlists; no more global list
        self.max_playlists = 10

        self.imageID = 0
        self.debug = False

        # Display text settings
        self.displayText = ""           # Mode4: line2
        self.subjectText = "Lyrion"     # line1
        self.displayDuration = 60

        # Logging and initialization tracking
        self.initialized = False
        self.createdDevices = 0

        # Track-change detection
        self.lastTrackIndex = {}

        # Nieuwe variabelen voor server-status tracking
        self.server_was_online = None   # None = nog niet bekend, daarna True/False

        self.last_success = 0
        self.offline_grace = 15  # seconden


    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------
    def log(self, msg):
        Domoticz.Log(msg)

    def log_player(self, dev, action):
        if not dev:
            name = "Unknown"
        else:
            name = dev.Name.replace(" Control", "")  # verwijdert suffix Control
        self.log(f"{name} | {action}")

    def debug_log(self, msg):
        if self.debug:
            Domoticz.Log(f"DEBUG: {msg}")

    def error(self, msg):
        Domoticz.Error(msg)

    @staticmethod
    def is_main_device_name(name: str) -> bool:
        """True als dit het hoofd-device is (geen Volume/Track/... suffix)."""
        return not any(x in name for x in ("Volume", "Track", "Actions", "Shuffle", "Repeat", "Playlists"))

    # ------------------------------------------------------------------
    # Domoticz lifecycle
    # ------------------------------------------------------------------
    def onStart(self):
        self.log(f"Starting Plugin version {Parameters['Version']}")

        _IMAGE = "lyrion"
        creating_new_icon = _IMAGE not in Images
        Domoticz.Image(f"{_IMAGE}.zip").Create()

        if _IMAGE in Images:
            self.imageID = Images[_IMAGE].ID
            if creating_new_icon:
                self.log("Icons created and loaded.")
            else:
                self.log(f"Icons found in database (ImageID={self.imageID}).")
        else:
            self.error(f"Unable to load icon pack '{_IMAGE}.zip'")

        self.pollInterval = int(Parameters.get("Mode1", 30))
        self.max_playlists = int(Parameters.get("Mode2", 50))
        self.debug = Parameters.get("Mode3", "False").lower() == "true"

        self.displayText = Parameters.get("Mode4", "")
        self.log(f"Display text = '{self.displayText}'")
        self.log(f"Starting initialization ......  Please wait ")

        self.url = f"http://{Parameters['Address']}:{Parameters['Port']}/jsonrpc.js"

        user = Parameters.get("Username", "")
        pwd = Parameters.get("Password", "")
        self.auth = (user, pwd) if user else None

        Domoticz.Heartbeat(5)
        self.nextPoll = time.time() + 10

    def onStop(self):
        self.log("Plugin stopped.")

    def onHeartbeat(self):
        if time.time() >= self.nextPoll:
            self.nextPoll = time.time() + self.pollInterval
            self.updateEverything()

    # ------------------------------------------------------------------
    # LMS JSON helper
    # ------------------------------------------------------------------
    def lms_query_raw(self, player, cmd_array):
        data = {"id": 1, "method": "slim.request", "params": [player, cmd_array]}
        try:
            r = requests.post(self.url, json=data, auth=self.auth, timeout=10)
            r.raise_for_status()
            result = r.json().get("result")

            self.last_success = time.time()

            if self.server_was_online is not True:
                if self.server_was_online is False:
                    self.log("Lyrion Music Server is back ONLINE.")
                self.server_was_online = True

            return result

        except Exception as e:
            now = time.time()

            # pas offline melden als grace period verstreken is
            if self.server_was_online is not False:
                if now - self.last_success > self.offline_grace:
                    self.log("Lyrion Music Server is OFFLINE")
                    self.server_was_online = False

            self.debug_log(f"LMS query failed: {e}")
            return None

    def get_serverstatus(self):
        return self.lms_query_raw("", ["serverstatus", 0, 999])

    def get_status(self, playerid):
        return self.lms_query_raw(playerid, ["status", "-", 1, "tags:adclmntyK"])

    def send_playercmd(self, playerid, cmd_array):
        return self.lms_query_raw(playerid, cmd_array)

    def send_button(self, playerid, button):
        return self.send_playercmd(playerid, ["button", button])

    # ------------------------------------------------------------------
    # DISPLAY TEXT
    # ------------------------------------------------------------------
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
            "font:large",
        ]

        self.send_playercmd(playerid, cmd)
        self.log(f"Display text sent to {playerid}: '{line1}' / '{line2}' ({d}s)")

    # ------------------------------------------------------------------
    # DEVICE CREATION / LOOKUP
    # ------------------------------------------------------------------
    def create_player_devices(self, name, mac):
        base = name
        unit = 1
        while unit in Devices:
            unit += 10

        # main selector
        opts_main = {
            "LevelNames": "Off|Pause|Play|Stop",
            "LevelActions": "||||",
            "SelectorStyle": "0",
        }

        Domoticz.Device(
            Name=f"{base} Control",
            Unit=unit,
            TypeName="Selector Switch",
            Switchtype=18,
            Options=opts_main,
            Image=self.imageID,
            Description=mac,
            Used=1,
        ).Create()

        # volume
        Domoticz.Device(
            Name=f"{base} Volume",
            Unit=unit + 1,
            Type=244,
            Subtype=73,
            Switchtype=7,
            Image=5,
            Description=mac,
            Used=1,
        ).Create()

        # track text
        Domoticz.Device(
            Name=f"{base} Track",
            Unit=unit + 2,
            TypeName="Text",
            Image=self.imageID,
            Description=mac,
            Used=1,
        ).Create()

        # actions selector
        opts_act = {
            "LevelNames": "None|SendText|Sync to this|Unsync",
            "LevelActions": "||",
            "SelectorStyle": "0",
        }

        Domoticz.Device(
            Name=f"{base} Actions",
            Unit=unit + 3,
            TypeName="Selector Switch",
            Switchtype=18,
            Options=opts_act,
            Image=self.imageID,
            Description=mac,
            Used=1,
        ).Create()

        # shuffle selector
        opts_shuffle = {
            "LevelNames": "Off|Songs|Albums",
            "LevelActions": "||",
            "SelectorStyle": "0",
        }

        Domoticz.Device(
            Name=f"{base} Shuffle",
            Unit=unit + 4,
            TypeName="Selector Switch",
            Switchtype=18,
            Options=opts_shuffle,
            Image=self.imageID,
            Description=mac,
            Used=1,
        ).Create()

        # repeat selector
        opts_repeat = {
            "LevelNames": "Off|Track|Playlist",
            "LevelActions": "||",
            "SelectorStyle": "0",
        }

        Domoticz.Device(
            Name=f"{base} Repeat",
            Unit=unit + 5,
            TypeName="Selector Switch",
            Switchtype=18,
            Options=opts_repeat,
            Image=self.imageID,
            Description=mac,
            Used=1,
        ).Create()

        # playlists selector
        opts_pl = {
            "LevelNames": "Select|Loading...",
            "LevelActions": "",
            "SelectorStyle": "1",
        }

        Domoticz.Device(
            Name=f"{base} Playlists",
            Unit=unit + 6,
            TypeName="Selector Switch",
            Switchtype=18,
            Options=opts_pl,
            Image=self.imageID,
            Description=mac,
            Used=1,
        ).Create()

        self.createdDevices += 7
        self.log(f"Devices created for player '{name}'")
        return (unit, unit + 1, unit + 2, unit + 3, unit + 4, unit + 5, unit + 6)

    def find_player_devices(self, mac):
        main = vol = text = actions = shuffle = repeat = playlistsel = None

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
            elif dev.Name.endswith("Playlists"):
                playlistsel = uid
            else:
                main = uid

        if main:
            return (main, vol, text, actions, shuffle, repeat, playlistsel)
        return None

    # ------------------------------------------------------------------
    # PLAYER-SPECIFIC PLAYLISTS
    # ------------------------------------------------------------------
    def get_player_playlists(self, mac):
        result = self.send_playercmd(mac, ["playlists", 0, self.max_playlists])
        if not result:
            return []

        pl_loop = result.get("playlists_loop", []) or []
        playlists = []
        for p in pl_loop[: self.max_playlists]:
            name = p.get("playlist", "")
            plid = p.get("id")
            if name:
                playlists.append({"id": plid, "playlist": name})
        return playlists

    def update_player_playlist_selector(self, plsel_unit, playlists, active_playlist_name=None):
        if plsel_unit not in Devices:
            return

        dev_pl = Devices[plsel_unit]

        if not playlists:
            levelnames = "Select|No playlists"
        else:
            levelnames = "Select|" + "|".join(p["playlist"] for p in playlists)

        opts = {
            "LevelNames": levelnames,
            "LevelActions": "",
            "SelectorStyle": "1",
        }

        if dev_pl.Options.get("LevelNames", "") != levelnames:
            dev_pl.Update(nValue=0, sValue=dev_pl.sValue, Options=opts)
            dev_pl = Devices[plsel_unit]
            self.log(f"Playlist selector updated for '{dev_pl.Name}'.")

        if active_playlist_name and playlists:
            for idx, pinfo in enumerate(playlists):
                if pinfo["playlist"] == active_playlist_name:
                    expected_level = (idx + 1) * 10
                    if dev_pl.sValue != str(expected_level):
                        self.log(f"Setting playlist selector '{dev_pl.Name}' to level {expected_level} for '{active_playlist_name}'")
                        dev_pl.Update(nValue=0, sValue=str(expected_level))
                    break
        else:
            if dev_pl.sValue != "0":
                dev_pl.Update(nValue=0, sValue="0")

    def play_playlist_for_player(self, mac, Level):
        if Level == 0:
            self.log("Playlist selection reset to 'Select'.")
            return

        if Level < 10:
            return

        playlists = self.get_player_playlists(mac)
        idx = int(Level // 10) - 1
        if idx < 0 or idx >= len(playlists):
            self.error("Invalid playlist index.")
            return

        pl = playlists[idx]
        playlist_name = pl["playlist"]
        playlist_id = pl["id"]

        self.send_playercmd(mac, ["playlistcontrol", "cmd:load", f"playlist_id:{playlist_id}"])
        self.log(f"Loaded playlist '{playlist_name}' (ID {playlist_id}) on player {mac}")
        self.nextPoll = time.time() + 1

    # ------------------------------------------------------------------
    # MAIN UPDATE LOOP
    # ------------------------------------------------------------------
    def updateEverything(self):
        server = self.get_serverstatus()
        if not server:
            # Geen extra log hier meer – melding komt al uit lms_query_raw
            return

        self.players = server.get("players_loop", []) or []

        for p in self.players:
            name = p.get("name", "Unknown")
            mac = p.get("playerid", "")
            if mac and not self.find_player_devices(mac):
                self.create_player_devices(name, mac)

        for p in self.players:
            mac = p.get("playerid")
            if not mac:
                continue

            devices = self.find_player_devices(mac)
            if not devices:
                continue

            main, vol, text, actions, shuffle, repeat, plsel = devices
            st = self.get_status(mac) or {}

            power = int(st.get("power", 0))
            mode = st.get("mode", "stop")

            sel_level = {"pause": 10, "play": 20, "stop": 30}.get(mode, 0)
            if power == 0:
                sel_level = 0

            if main in Devices:
                dev_main = Devices[main]
                n = 1 if power else 0
                s = str(sel_level)
                if dev_main.nValue != n or dev_main.sValue != s:
                    dev_main.Update(nValue=n, sValue=s)

            if vol in Devices:
                dev_vol = Devices[vol]
                old = int(dev_vol.sValue) if dev_vol.sValue.isdigit() else 0
                raw = st.get("mixer volume", old)
                try:
                    new = int(float(str(raw).replace("%", "")))
                except:
                    new = old
                if new != old:
                    dev_vol.Update(nValue=1 if new > 0 else 0, sValue=str(new))

            if text in Devices:
                dev_text = Devices[text]

                if power == 0 or mode in ["stop", "pause"]:
                    if dev_text.sValue != " ":
                        dev_text.Update(nValue=0, sValue=" ")
                    player_pl = self.get_player_playlists(mac)
                    self.update_player_playlist_selector(plsel, player_pl, active_playlist_name=None)
                    continue

                remote = st.get("remote", 0)
                rm = st.get("remoteMeta", {})
                pl_loop = st.get("playlist_loop", [])

                title = ""
                artist = ""

                if remote and rm:
                    title = rm.get("title", "") or title
                    artist = rm.get("artist", "") or artist

                if not title and isinstance(pl_loop, list) and pl_loop:
                    title = pl_loop[0].get("title", "") or title
                    artist = pl_loop[0].get("artist", "") or artist

                if not title:
                    title = st.get("current_title", "")

                if not title:
                    label = " "
                elif artist:
                    label = f"&#127908; {artist}<br>&#127925; {title}"
                else:
                    label = title

                label = label[:255]

                track_index = st.get("playlist_cur_index")
                player_key = mac
                changed = False

                if track_index is not None:
                    if player_key not in self.lastTrackIndex or self.lastTrackIndex[player_key] != track_index:
                        changed = True
                        self.lastTrackIndex[player_key] = track_index

                if dev_text.sValue != label or changed:
                    dev_text.Update(nValue=0, sValue=label)

            if shuffle in Devices:
                dev_shuffle = Devices[shuffle]
                try:
                    shuffle_state = int(st.get("playlist shuffle", 0))
                except Exception:
                    shuffle_state = 0
                level = shuffle_state * 10
                if dev_shuffle.sValue != str(level):
                    mode_name = {0: "Off", 1: "Songs", 2: "Albums"}.get(shuffle_state, shuffle_state)
                    self.log_player(dev_shuffle, f"Shuffle {mode_name}")
                    dev_shuffle.Update(nValue=0, sValue=str(level))

            if repeat in Devices:
                dev_repeat = Devices[repeat]
                try:
                    repeat_state = int(st.get("playlist repeat", 0))
                except Exception:
                    repeat_state = 0
                level = repeat_state * 10
                if dev_repeat.sValue != str(level):
                    mode_name = {0: "Off", 1: "Track", 2: "Playlist"}.get(repeat_state, repeat_state)
                    self.log_player(dev, f"Repeat {mode_name}")
                    dev_repeat.Update(nValue=0, sValue=str(level))

            player_pl = self.get_player_playlists(mac)
            playlist_tracks = st.get("playlist_tracks", 0)
            playlist_name = st.get("playlist_name", "")
            remote = st.get("remote", 0)

            playlist_is_active = (playlist_tracks > 1 and playlist_name not in ("", None) and remote == 0)

            if playlist_is_active:
                self.update_player_playlist_selector(plsel, player_pl, active_playlist_name=playlist_name)
            else:
                self.update_player_playlist_selector(plsel, player_pl, active_playlist_name=None)

        if not self.initialized:
            self.log("Initialization complete:")
            self.log(f" Players           : {len(self.players)}")
            device_count = len(Devices)
            self.log(f" Devices           : {device_count}")
            self.log(f" Max playlists/player : {self.max_playlists}")
            self.log(f" Poll interval     : {self.pollInterval} sec")
            self.initialized = True

    # ------------------------------------------------------------------
    # COMMAND HANDLER
    # ------------------------------------------------------------------
    def onCommand(self, Unit, Command, Level, Hue):
        if Unit not in Devices:
            return

        dev = Devices[Unit]
        devname = dev.Name
        mac = dev.Description

        self.debug_log(f"onCommand: Unit={Unit}, Name={devname}, Command={Command}, Level={Level}, mac={mac}")

        if "Playlists" in devname and Command == "Set Level":
            if Level == 0:
                dev.Update(nValue=0, sValue="0")
                return
            self.play_playlist_for_player(mac, Level)
            return

        if "Actions" in devname and Command == "Set Level":
            self.handle_actions(dev, mac, Level)
            return

        if "Shuffle" in devname:
            if Command == "Set Level":
                mode = int(Level // 10)
            elif Command == "Off":
                mode = 0
                Level = 0
            else:
                return

            self.send_playercmd(mac, ["playlist", "shuffle", str(mode)])
            nval = 1 if mode > 0 else 0
            dev.Update(nValue=nval, sValue=str(Level))
            mode_name = {0: "Off", 1: "Songs", 2: "Albums"}.get(mode, f"Unknown ({mode})")
            self.log_player(dev, f"Shuffle {mode_name}")
            return

        if "Repeat" in devname:
            if Command == "Set Level":
                mode = int(Level // 10)
            elif Command == "Off":
                mode = 0
                Level = 0
            else:
                return

            self.send_playercmd(mac, ["playlist", "repeat", str(mode)])
            nval = 1 if mode > 0 else 0
            dev.Update(nValue=nval, sValue=str(Level))
            mode_name = {0: "Off", 1: "Track", 2: "Playlist"}.get(mode, f"Unknown ({mode})")
            self.log_player(dev_repeat, f"Repeat {mode_name}")
            return

        if Command in ["On", "Off"] and self.is_main_device_name(devname):
            self.handle_power(dev, mac, Command)
            return

        if "Volume" in devname and Command == "Set Level":
            self.handle_volume(dev, mac, Level)
            return

        if Command == "Set Level" and self.is_main_device_name(devname):
            self.handle_main_playback(dev, mac, Level)
            return

    # ------------------------------------------------------------------
    # Command helpers
    # ------------------------------------------------------------------
    def handle_actions(self, dev, mac, Level):
        if Level == 10:
            if not self.displayText:
                self.error("Message text (Mode4) is empty.")
                return
            self.send_display_text(mac, self.displayText)
            dev.Update(nValue=1, sValue=str(Level))
            self.log_player(dev, "SendText")
            return

        if Level == 20:
            self.log(f"Syncing all players TO master: {mac}")
            server = self.get_serverstatus()
            if not server:
                self.error("Cannot sync: server not responding.")
                return
            players = server.get("players_loop", [])
            if not players:
                self.error("No players found to sync.")
                return
            for p in players:
                other_mac = p.get("playerid")
                if other_mac and other_mac != mac:
                    self.log(f" -> syncing {other_mac} to master {mac}")
                    self.send_playercmd(other_mac, ["sync", mac])
            dev.Update(nValue=1, sValue=str(Level))
            return

        if Level == 30:
            self.log_player(dev, "Unsync")
            self.send_playercmd(mac, ["sync", "-"])
            dev.Update(nValue=1, sValue=str(Level))
            return

    def handle_power(self, dev, mac, Command):
        self.send_playercmd(mac, ["power", "1" if Command == "On" else "0"])
        dev.Update(nValue=1 if Command == "On" else 0, sValue="")
        self.log_player(dev, f"Power {Command}")

    def handle_volume(self, dev, mac, Level):
        self.send_playercmd(mac, ["mixer", "volume", str(Level)])
        dev.Update(nValue=1 if Level > 0 else 0, sValue=str(Level))
        self.log_player(dev, f"Volume {Level}%")

    def handle_main_playback(self, dev, mac, Level):
        btn_map = {
            10: ("pause.single", "Pause"),
            20: ("play.single", "Play"),
            30: ("stop", "Stop"),
        }
        if Level not in btn_map:
            return
        cmd, label = btn_map[Level]
        self.send_button(mac, cmd)
        dev.Update(nValue=1, sValue=str(Level))
        self.log_player(dev, label)


# -------------------------------------------------------------------
# DOMOTICZ HOOKS
# -------------------------------------------------------------------
_plugin = LMSPlugin()

def onStart():
    _plugin.onStart()

def onStop():
    _plugin.onStop()

def onHeartbeat():
    _plugin.onHeartbeat()

def onCommand(Unit, Command, Level, Hue):
    _plugin.onCommand(Unit, Command, Level, Hue)
