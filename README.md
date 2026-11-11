# LoupixDeck Profiles

Community profiles for [LoupixDeck](https://github.com/RadiatorTwo/LoupixDeck). Each profile is a
`.loupixprofile` package exported from the app, together with a short description and a preview
image.

LoupixDeck reads [`index.json`](index.json) to list the profiles and downloads the package from
this repository. The index is built automatically from the `profiles/` folder; nobody edits it by
hand.

## Using a profile

Open the profile browser in LoupixDeck, pick a profile and install it. You can also download a
`.loupixprofile` file from `profiles/` and import it from the profile menu.

A profile can contain commands that start programs, send key presses or run macros. The app shows
the commands and required plugins before it imports a profile. Read them before you accept.

## Sharing a profile

See [CONTRIBUTING.md](CONTRIBUTING.md). In short: export your profile from LoupixDeck, put it in
`profiles/<your-github-name>/<profile-id>/` with a `profile.json` and a `preview.png`, and open a
pull request.

## Layout

```
index.json                 generated list of all profiles (do not edit)
index.schema.json          JSON schema of index.json
profile.schema.json        JSON schema of a submission's profile.json
profiles/
  <author>/                your GitHub user name
    <profile-id>/          unique id, lower-case letters, digits and dashes
      profile.json         name, description, version, tags, ...
      <profile-id>.loupixprofile
      preview.png          main image shown in the app (or preview.jpg)
      screenshots/         optional, up to 6 PNG or JPEG files
      README.md            optional, longer description
scripts/build_index.py     validates submissions and builds index.json
templates/profile.json     starting point for your profile.json
```

## Index format

`index.json` follows [`index.schema.json`](index.schema.json). Every entry combines the fields from
the author's `profile.json` with data read from the package's own `manifest.json` (device, kind,
required plugins, commands, macros, format versions), plus the download URL, size and SHA-256 of
the package. The app refuses a download whose hash does not match.

## Reporting a profile

If a profile is broken, misleading or harmful, open an issue with a link to its folder.
