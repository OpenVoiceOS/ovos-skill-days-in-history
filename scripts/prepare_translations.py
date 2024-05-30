"""this script should run every time the contents of the locale folder change
except if PR originated from @gitlocalize-app
TODO - on commit to dev
"""

import json
from os.path import dirname
import os

locale = f"{dirname(dirname(__file__))}/locale"
tx = f"{dirname(dirname(__file__))}/translations"


for lang in os.listdir(locale):
    intents = {}
    dialogs = {}
    vocs = {}
    regexes = {}
    for root, _, files in os.walk(f"{locale}/{lang}"):
        b = root.split(f"/{lang}")[-1]

        for f in files:
            if b:
                fid = f"{b}/{f}"
            else:
                fid = f
            with open(f"{root}/{f}") as fi:
                strings = [l.replace("{{", "{").replace("}}", "}")
                           for l in fi.read().split("\n") if l.strip()
                           and not l.startswith("#")]

            if fid.endswith(".intent"):
                intents[fid] = strings
            elif fid.endswith(".dialog"):
                dialogs[fid] = strings
            elif fid.endswith(".voc"):
                vocs[fid] = strings
            elif fid.endswith(".rx"):
                regexes[fid] = strings

    os.makedirs(f"{tx}/{lang.lower()}", exist_ok=True)
    if intents:
        with open(f"{tx}/{lang.lower()}/intents.json", "w") as f:
            json.dump(intents, f, indent=4)
    if vocs:
        with open(f"{tx}/{lang.lower()}/vocabs.json", "w") as f:
            json.dump(vocs, f, indent=4)
    if regexes:
        with open(f"{tx}/{lang.lower()}/regexes.json", "w") as f:
            json.dump(regexes, f, indent=2)
    if dialogs:
        dialogs = {k: sorted(v) for k, v in dialogs.items()}
        if len(dialogs) > 50:
            files = list(dialogs.items())
            i = 0
            while len(files):
                i += 1
                chunk, files = files[:50], files[50:]
                with open(f"{tx}/{lang.lower()}/dialogs_{i}.json", "w") as f:
                    json.dump({k:v for k, v in chunk}, f, indent=2)
        else:
            with open(f"{tx}/{lang.lower()}/dialogs.json", "w") as f:
                json.dump(dialogs, f, indent=2)
