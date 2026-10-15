# Public artifact inventory

| Artifact | Distribution | Requirement |
| --- | --- | --- |
| AI1 processed Parquets, profiles, embedding vectors/IDs/mapping and manifest | Separate `ai1-demo-data.zip`; Git-ignored | Download through [DATA_DOWNLOAD.txt](../data/DATA_DOWNLOAD.txt), then run setup |
| `models/ranker/catboost_yetirank.cbm` | Ordinary Git file, 15-feature runtime model | Included in clone; never retrained by setup |
| `models/ranker/restaurant-ranker-v3-catboost.cbm` | Ordinary Git file, historical 11-feature model | Retained for compatibility/history; incompatible with current runtime feature order |
| AI2 V3 adapter config and chat template | Ordinary Git text files | Reference configuration for optional local inference |
| AI2 adapter weights and tokenizer bundle | External, not Git/LFS | Obtain matching files separately; no public automatic download is configured |
| `Qwen/Qwen3-1.7B` | External Hugging Face model/cache | Only needed when explicitly enabling local Qwen |
| `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` | External Hugging Face model/cache | Needed for live query encoding; existing lazy loader can download it |

The synthetic demo has its own manifest/card and count metadata. Validation binds every packaged payload file to the manifest, validates source/vector/profile hashes, shapes, IDs and menu mapping. Matching metadata/card determines demo counts; legacy V3 counts must not be substituted. A valid active dataset short-circuits ZIP provisioning, so it does not verify a newly supplied ZIP.

Private interaction/labeling files, `.env`, database contents, model caches, backups, generated builds and archives are not distributed. No LFS pointer or remote LFS object is required by a public clone. Optional adapter instructions do not claim that external weights are available or inference has been tested.

Successful artifact validation does not verify real-world restaurant facts, recommendation quality or model training provenance. Existing contributor and third-party notices are retained; see [third-party notices](../THIRD_PARTY_NOTICES.md).
