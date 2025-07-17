## Telegram export tool.

### Installation
```shell
$ pip install t-export
```

### Usage
```shell
Usage: python -m texport [OPTIONS]

Options:
  --api-id INTEGER                Telegram api id. Saved in
                                  ~/.texport/config.json file.
  --api-hash TEXT                 Telegram api hash. Saved in
                                  ~/.texport/config.json file.
  -s, --session-name TEXT         Pyrogram session name or path to existing
                                  file. Saved in
                                  ~/.texport/<session_name>.session file.
  -c, --chat-id TEXT              Chat id or username or phone number. "me" or
                                  "self" to export saved messages.
  -o, --output TEXT               Output directory.
  -l, --size-limit INTEGER        Media size limit in megabytes.
  -f, --from-date TEXT            Date from which messages will be saved.
  -t, --to-date TEXT              Date to which messages will be saved.
  --photos / --no-photos          Download photos or not.
  --videos / --no-videos          Download videos or not.
  --voice / --no-voice            Download voice messages or not.
  --video-notes / --no-video-notes
                                  Download video messages or not.
  --stickers / --no-stickers      Download stickers or not.
  --gifs / --no-gifs              Download gifs or not.
  --documents / --no-documents    Download documents or not.
  -q, --quiet                     Do not print progress to console.
  --no-preload                    Do not preload all messages.
  -d, --max-concurrent-downloads INTEGER
                                  Number of concurrent media downloads.
  --takeout                       Use takeout api.
  --no-count                      Do not count messages that will be exported.
  -w, --write-threshold INTEGER   Messages write threshold.
  --all-media-wait                Write messages without waiting for ALL media
                                  to download.
  --help                          Show this message and exit.
```
At first run you will need to specify api id and api hash and log in into your telegram account.
Or you can pass path of existing pyrogram session to "--session" argument (no need to logging in or specifying api id or api hash).

### Examples

#### Export all messages from private chat with user @example to directory example_export
```shell
$ t-export -c example -o example_export
```

#### Export all messages from private chat with user @example to directory example_export without videos and with size limit of 100 megabytes
```shell
$ t-export -c example -o example_export --no-videos --size-limit 100
```

#### Export all messages from start of 2023 from private chat with user @example to directory example_export
```shell
$ t-export -c example -o example_export --size-limit 100 --from-date 01.01.2023
```