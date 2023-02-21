#!/usr/bin/env python3
import requests
import json
import argparse
from datetime import datetime
import sys
import os
from pathlib import Path
import gi
gi.require_version("Gst", "1.0")  # noqa
gi.require_version("GstTag", "1.0")  # noqa
from gi.repository import Gst, GLib, GstTag  # noqa
Gst.init(None)


class PlixusAERClient:
    def __init__(self, conf):
        self.conf = conf
        self.media_folder = Path(conf.media_folder)

    def run(self):
        method = getattr(self, self.conf.command)
        method()

    def do_request(self, path, method="get", data=None):
        url_full = "http://%s:8890/CoCon/" % self.conf.device_ip + path
        method_fct = getattr(requests, method)
        suffix = path.split("/")[-1]
        d = json.loads(method_fct(url_full, data=data).json())[suffix]
        return d

    def start_recording(self):
        s = self.do_request("Recording/StartRecording")["RecordingState"]
        if s != "active":
            print("Failed to start recording on %s" % self.conf.device_ip)
            sys.exit(1)
        else:
            print("Recording started on %s" % self.conf.device_ip)

    def stop_recording(self):
        if self.conf.media_folder is not None:
            self.lock_media_folder()
        s = self.do_request("Recording/StopRecording")["RecordingState"]
        if s != "idle":
            print("Failed to stop recording on %s" % self.conf.device_ip)
            self.unlock_media_folder()
            sys.exit(1)
        else:
            print("Recording stopped on %s" % self.conf.device_ip)
        if self.conf.media_folder is not None:
            self.download_audio_files()
            self.mux_files()
        self.unlock_media_folder()
        print("Finished")

    def list_files(self):
        mp3_files = self.get_files()
        print(f"Found: {mp3_files}")

    def lock_media_folder(self):
        print("Locking media folder %s" % self.conf.media_folder)
        path = self.media_folder / "recording_stopped_script_running"
        path.touch()

    def unlock_media_folder(self):
        if self.conf.media_folder:
            print("Unlocking media folder %s" % self.conf.media_folder)
            path = self.media_folder / "recording_stopped_script_running"
            if path.exists():
                path.unlink()
            else:
                print("Error, cannot unlock media folder: %s file not found" % path)

    def find_files_by_extension(self, extension):
        return self.media_folder.glob(extension)

    def mux_files(self):
        input_file = self.find_files_by_extension("*.mp4")[0]
        output_file = input_file.replace(".mp4", "_multitrack.mp4")
        p = "filesrc location={input_file} ! qtdemux name=demux demux. ! queue ! video/x-h264 ! queue ! mp4mux name=mux ! filesink location={output_file} demux. ! audio/mpeg ! queue ! mux.".format(**locals())
        for mp3 in self.find_files_by_extension("*.mp3"):
            lang = self.get_lang(mp3)
            p += " filesrc location=%s ! decodebin ! audioconvert %s! fdkaacenc ! mux." % (mp3, '! taginject tags="language-code=%s" ' % lang if lang else "")
        pipeline = Gst.parse_launch(p)
        bus = pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::eos", self.on_eos, pipeline, input_file, output_file)
        print("Muxing files")
        pipeline.set_state(Gst.State.PLAYING)
        self.ml = GLib.MainLoop()
        self.ml.run()

    def get_lang(self, mp3):
        try:
            # fr, en, https://fr.wikipedia.org/wiki/Liste_des_codes_ISO_639-1
            lang = mp3.split("_")[-1].replace(".mp3", "").split("-")[1].lower()
            lang_iso_639_2 = GstTag.tag_get_language_code_iso_639_2T(lang)
            if lang_iso_639_2 is not None:
                print("Detected language %s" % lang_iso_639_2)
                return lang_iso_639_2
            else:
                print("Language code %s is not ISO 639-2" % lang)
        except Exception:
            print("Failed to extract language from %s" % mp3)

    def on_eos(self, bus, msg, pipeline, input_file, output_file):
        print("Muxing finished")
        pipeline.set_state(Gst.State.NULL)
        self.ml.quit()
        print("Renaming files")
        os.rename(input_file, input_file + ".bak")
        os.rename(output_file, input_file)

    def download_audio_files(self):
        with open(self.media_folder / 'metadata.json', 'r') as f:
            m = json.load(f)
            creation = datetime.fromisoformat(m["creation"])
            mp3_files = self.get_files(datetime.strftime(creation, "%Y-%m-%d_%Hh%Mm%Ss"))
            if not mp3_files:
                print("No files found")
                self.unlock_media_folder()
                sys.exit(1)
            else:
                for f in mp3_files.values():
                    self.download_file(f["url"], self.conf.media_folder)

    def download_file(self, url, dest_folder):
        local_filename = os.path.join(dest_folder, url.split("/")[-1])
        print("Downloading %s to %s" % (url, local_filename))
        with requests.get(url, stream=True) as r:
            r.raise_for_status()
            with open(local_filename, "wb") as f:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:  # filter out keep-alive new chunks
                        f.write(chunk)
        if os.path.getsize(local_filename) == 0:
            raise Exception("File %s was empty" % url)
        print("File %s download finished" % url)

    def get_recording_state(self):
        #active,error,idle,paused,unknown.
        state = self.do_request("Recording/GetRecordingState")["RecordingState"]
        print("Recording state on %s is %s " % (self.conf.device_ip, state))

    def parse_filename(self, url):
        # http://192.168.40.35/audio/internal/Ubicast_test_2020-01-20_13h42m26s_02-FR_01_00.mp3
        fname = url.split("/")[-1].replace(".mp3", "")
        try:
            if self.conf.prefix:
                fname = fname.replace(self.conf.prefix + "_", "")
            day, hour, channel = fname.split("_")
            time = datetime.strptime("%s_%s" % (day, hour), "%Y-%m-%d_%Hh%Mm%Ss")
        except Exception as e:
            # Recording
            # =========
            # disable "Automatically split the recording files after every hour"
            # enable "Automatically delete oldest files when storage is full"
            # Regional settings
            # =================
            # YYYY-MM-DD
            # time format: hh:mm (24h)
            # It is critical that both devices have a close enough clock
            print('Failed to parse filename %s, check that the prefix is correct and disable "Automatically split the recording files after every hour"' % url)
            print(e)
            time = None
            channel = "Unknown"
        return time, channel

    def get_files(self, start_time_string=None):
        d = self.do_request("Recording/GetRecordingFilesInfo")["RecordingFilesInfo"][0]["RecordingFiles"]
        files = {}
        for f in d:
            time, channel = self.parse_filename(f["Name"])
            if "Floor" in channel and not self.conf.include_floor:
                continue
            url = requests.compat.urljoin("http://%s" % self.conf.device_ip, f["Name"])
            if time is not None and start_time_string is not None:
                start_time = datetime.strptime(start_time_string, "%Y-%m-%d_%Hh%Mm%Ss")
                diff = abs(time - start_time)
                # we are assuming that the plixus will sort by date (more recent last)
                # we only want to keep the last file for every channel
                if diff.seconds <= self.conf.tolerance_s:
                    files[channel] = {
                        "time": time,
                        "url": url,
                    }
            elif start_time_string is None:
                files[channel] = {
                    "time": time,
                    "url": url,
                }
        if not files:
            print("No audio files found for start timestamp %s, check clock sync or increase tolerance" % start_time_string)
        else:
            print("Found files: %s" % [f["url"] for f in files.values()])
        return files


if __name__ == "__main__":
    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    commands = [
        "start_recording",
        "stop_recording",
        "get_recording_state",
        "list_files",
    ]

    parser.add_argument(
        "media_folder",
        type=str,
        nargs="?",
        help="media folder path",
    )

    parser.add_argument(
        "-d",
        "--device-ip",
        type=str,
        help="Televic device IP",
        required=True,
    )

    parser.add_argument(
        "--include-floor",
        "-f",
        action="store_true",
        help="Include floor channel",
    )

    parser.add_argument(
        "--prefix",
        "-p",
        type=str,
        default="",
        help="Prefix to look for when downloading files, e.g. RoomA (RoomA_2020-06-17_15h22m56s_Floor.mp3)",
    )

    parser.add_argument(
        "-t",
        "--tolerance-s",
        type=int,
        help="Tolerance offset in seconds",
        default=30,
    )

    parser.add_argument(
        "-c",
        "--command",
        type=str,
        required=True,
        help="Command among: %s" % (" ".join(commands))
    )

    args = parser.parse_args()

    if args.command in ["stop_recording"] and args.media_folder is None:
        print("Media folder is mandatory for starting or stopping a recording, exiting")
        sys.exit(0)

    if args.command not in commands:
        print("Invalid command")
        parser.print_help()
        sys.exit(1)

    try:
        c = PlixusAERClient(args)
        c.run()
    except Exception as e:
        print("Exception occured: %s, exiting" % e)
        # unlock media so that recorder does not get stuck
        c.unlock_media_folder()
        sys.exit(1)
