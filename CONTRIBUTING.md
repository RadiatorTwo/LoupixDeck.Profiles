# Contributing a profile

## 1. Export the profile

In LoupixDeck, export the profile, workspace or page you want to share. The app writes a
`.loupixprofile` file. Before you export, remove anything private: names, file paths, URLs with
tokens, passwords in macros, and so on.

## 2. Create your folder

Fork this repository and create:

```
profiles/<your-github-name>/<profile-id>/
```

- `<your-github-name>` must be your GitHub user name. You can only change files in your own folder.
- `<profile-id>` is lower-case letters, digits and dashes, for example `obs-streaming-starter`. It
  must be unique in the repository and must not change later.

## 3. Add the files

| File | Required | Notes |
|---|---|---|
| `<profile-id>.loupixprofile` | yes | the exported package, renamed to the profile id, max 20 MB |
| `profile.json` | yes | copy [`templates/profile.json`](templates/profile.json) and fill it in |
| `preview.png` or `preview.jpg` | yes | a photo or screenshot of the device with the profile, max 2 MB |
| `screenshots/*.png` | no | up to 6 more images, max 2 MB each |
| `README.md` | no | longer description, setup notes |

`profile.json` fields:

| Field | Required | Notes |
|---|---|---|
| `id` | yes | same as the folder name |
| `name` | yes | max 60 characters |
| `description` | yes | max 500 characters |
| `author` | yes | your GitHub user name, same as the parent folder |
| `version` | yes | `major.minor.patch`; raise it with every change |
| `license` | no | SPDX id, default `CC-BY-4.0` |
| `tags` | no | up to 10 lower-case words, for example `streaming`, `obs` |
| `platforms` | no | `Windows`, `Linux`, `macOS`; omit if the profile works everywhere |

Do not add the device, the plugins or the commands. They are read from the package.

## 4. Check locally (optional)

```
python scripts/build_index.py --validate
```

## 5. Open a pull request

The pull request check validates your folder. Do not change `index.json`: it is rebuilt
automatically after the merge.

## Updating a profile

Replace the `.loupixprofile` file (keep the name), raise `version` in `profile.json`, and open a new
pull request.

## Rules

- By opening a pull request you license your profile under the `license` in its `profile.json`
  (default `CC-BY-4.0`).

- Only share profiles you made or have the right to share. Images inside the package must be yours
  or free to use.
- No commands that harm the user's system, collect data, or download and run software.
- Profiles that do not work, or that try to hide what they do, are removed.
