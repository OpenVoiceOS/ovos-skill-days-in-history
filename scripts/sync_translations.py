"""this script should run in every PR originated from @gitlocalize-app
TODO - before PR merge
"""

import json
from os.path import dirname
import os
from ovos_utils.bracket_expansion import expand_template
from ovos_utils.list_utils import flatten_list, deduplicate_list

locale = f"{dirname(dirname(__file__))}/locale"
tx = f"{dirname(dirname(__file__))}/translations"


for lang in os.listdir(tx):
    intents = f"{tx}/{lang}/intents.json"
    dialogs = f"{tx}/{lang}/dialogs.json"
    vocs = f"{tx}/{lang}/vocabs.json"
    regexes = f"{tx}/{lang}/regexes.json"

    os.makedirs(f"{locale}/{lang}", exist_ok=True)
    
    if os.path.isfile(intents):
        with open(intents) as f:
            data = json.load(f)
        for fid, samples in data.items():
            if samples:
                samples = deduplicate_list(flatten_list([expand_template(s.strip())
                                                         for s in samples
                                                         if s and s.strip() != "[UNUSED]"]))  # s may be None
                if fid.startswith("/"):
                    p = f"{locale}/{lang.lower()}{fid}"
                else:
                    p = f"{locale}/{lang.lower()}/{fid}"
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(f"{locale}/{lang.lower()}/{fid}", "w") as f:
                    f.write("\n".join(sorted(samples)))

    for f in os.listdir(f"{tx}/{lang}"):
        if f.startswith("dialogs") and f.endswith(".json"):
            dialogs = f"{tx}/{lang}/{f}"
        else:
            continue
        with open(dialogs) as f:
            data = json.load(f)
        for fid, samples in data.items():
            if samples:
                samples = deduplicate_list(flatten_list([expand_template(s.strip())
                                                         for s in samples
                                                         if s and s.strip() != "[UNUSED]"]))  # s may be None
                if fid.startswith("/"):
                    p = f"{locale}/{lang.lower()}{fid}"
                else:
                    p = f"{locale}/{lang.lower()}/{fid}"
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(f"{locale}/{lang.lower()}/{fid}", "w") as f:
                    f.write("\n".join(sorted(samples)))

    if os.path.isfile(vocs):
        with open(vocs) as f:
            data = json.load(f)
        for fid, samples in data.items():
            if samples:
                samples = deduplicate_list(flatten_list([expand_template(s.strip())
                                                         for s in samples
                                                         if s and s.strip() != "[UNUSED]"]))  # s may be None
                if fid.startswith("/"):
                    p = f"{locale}/{lang.lower()}{fid}"
                else:
                    p = f"{locale}/{lang.lower()}/{fid}"
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(f"{locale}/{lang.lower()}/{fid}", "w") as f:
                    f.write("\n".join(sorted(samples)))

    if os.path.isfile(regexes):
        with open(regexes) as f:
            data = json.load(f)
        for fid, samples in data.items():
            if samples:
                samples = deduplicate_list(flatten_list([expand_template(s.strip())
                                                         for s in samples
                                                         if s and s.strip() != "[UNUSED]"]))  # s may be None
                if fid.startswith("/"):
                    p = f"{locale}/{lang.lower()}{fid}"
                else:
                    p = f"{locale}/{lang.lower()}/{fid}"
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(f"{locale}/{lang.lower()}/{fid}", "w") as f:
                    f.write("\n".join(sorted(samples)))

