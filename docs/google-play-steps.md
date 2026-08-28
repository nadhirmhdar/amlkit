# Publishing the amlkit Android app to Google Play

The native app lives in `android/` (Kotlin + Jetpack Compose) and talks to
amlkit's JSON API at `amlkit/api/mobile.py` (`/api/v1/*`). This doc is the
path from a clean checkout to a release on the Play Store.

**Build verification note:** the app was authored in a sandbox with no
Android SDK and no network access to `dl.google.com`, so it has never been
compiled locally. `.github/workflows/android.yml` builds it on every push to
`android/**` — check that workflow is green before doing anything below. If
it's red, fix the build first; everything past this point assumes a green
build.

---

## 1. Point the app at a real server

The debug build defaults to `http://10.0.2.2:8000/` — the Android emulator's
alias for the host machine's own `localhost`, so it talks to
`python scripts/serve.py` running unmodified on a dev machine. That is not
reachable from a phone, and it's cleartext HTTP (only allowed for that one
emulator address — see `network_security_config.xml`). Before building for
real devices or for release:

1. Deploy amlkit somewhere with a real HTTPS URL (the repo already has a
   Cloud Run path — see `.github/workflows/source-canary.yml`'s `deploy` job
   and `scripts/deploy_gcp.ps1` — or any host that terminates TLS in front of
   `scripts/serve.py`; see the README's binding/TLS warning, which applies
   here just as much as to the web UI).
2. Build with that URL:
   ```bash
   ./gradlew assembleRelease -PapiBaseUrl=https://your-deployment.example.com/
   ```
   (trailing slash required — it's a Retrofit base URL). Baking this in at
   build time, rather than making it editable in-app, matches this repo's
   "loud failure, no silent drift" stance elsewhere: every build is
   traceably pointed at one server.

## 2. Pick a real application ID

`android/app/build.gradle.kts` currently sets:
```kotlin
applicationId = "com.amlkit.mobile"
```
**This is a placeholder.** The application ID is permanent the moment you
publish the first release to Play — it can never be changed afterward.
Change it to a reverse-domain id you actually control (e.g.
`com.yourfirm.amlkit`) before the first upload. `namespace` in the same
block (the Kotlin/resource package) can stay as-is; it doesn't need to match.

## 3. Upload keystore

`android/app/build.gradle.kts` already wires a `release` signing config that
reads its values from `android/local.properties` (gitignored, never
committed) — `bundleRelease`/`assembleRelease` are unsigned and fail loudly
until that file exists.

If a keystore doesn't exist yet, generate one once and keep it **forever** —
losing it means you can never update the app under the same Play listing
again:
```bash
keytool -genkeypair -v -keystore amlkit-upload.p12 -storetype PKCS12 \
  -alias amlkit -keyalg RSA -keysize 2048 -validity 10000
```
(PKCS12 uses one password for both the store and the key entry — keytool
will ignore a separately-specified `-keypass`, that's expected.)

Either way, store the `.p12`/`.jks` file and its password somewhere durable
and private — a password manager or secrets vault, never the repo — and
create `android/local.properties`:
```properties
RELEASE_STORE_FILE=/absolute/path/to/amlkit-upload.p12
RELEASE_STORE_PASSWORD=...
RELEASE_KEY_ALIAS=amlkit
RELEASE_KEY_PASSWORD=...
```

(Play App Signing, enabled by default for new apps, re-signs your upload
with Google's own key for distribution — this upload key only needs to
authenticate *you* to Google, so if it's ever lost, Google's account-recovery
process for Play App Signing is the way back in, not a dead end.)

## 4. Build the release bundle

Play requires an Android App Bundle, not an APK:
```bash
cd android
./gradlew bundleRelease -PapiBaseUrl=https://your-deployment.example.com/
```
Output: `android/app/build/outputs/bundle/release/app-release.aab`.

### Automated release builds

`.github/workflows/android-release.yml` does the same build in CI, on
demand (*Actions → Android release build → Run workflow*, filling in
`apiBaseUrl`, `versionCode`, and `versionName`) — useful once cutting a
release from a clean checkout matters more than doing it from whichever
machine happens to have the keystore on it.

It needs four repository secrets it cannot set for itself (*Settings →
Secrets and variables → Actions → New repository secret* — this step is
unavoidably manual: no agent or CI job should hold write access to your
repo's secrets, so this is the one piece of "automated release builds" that
stays a human action):

| Secret | Value |
|---|---|
| `ANDROID_KEYSTORE_BASE64` | `base64 -w0 amlkit-upload.p12` (the keystore file's base64 output, wrapped as text) |
| `ANDROID_KEYSTORE_PASSWORD` | the keystore's storepass |
| `ANDROID_KEY_ALIAS` | `amlkit` (or whatever `-alias` was used when generating it) |
| `ANDROID_KEY_PASSWORD` | same as `ANDROID_KEYSTORE_PASSWORD` for a PKCS12 keystore (see §3 — PKCS12 uses one password for both) |

The workflow decodes the keystore into the runner's ephemeral temp
directory and writes it into `android/local.properties` for the duration of
that one job only — nothing is persisted or logged. The resulting `.aab` is
attached to the workflow run as a downloadable artifact; uploading it to
Play Console (§6–7 below) is still a manual step, deliberately: publishing
directly from CI would need a Play Console service-account key added as a
*fifth* secret, a materially bigger trust decision than just building the
bundle, and one worth making on its own rather than as a side effect of this
setup.

## 5. Google Play Console setup

1. **Developer account** — [play.google.com/console](https://play.google.com/console),
   one-time $25 registration fee if you don't already have one.
2. **Create app** — Play Console → *Create app*. Name, default language,
   app/game = App, free/paid.
3. **Store listing** (*Grow → Store presence → Main store listing*):
   - App name, short description, and full description are drafted in
     `docs/play-store-listing.md` — copy-paste-ready, grounded in what the
     app actually does (Play policy requires accuracy, not just polish).
   - Screenshots (phone screenshots are mandatory — capture a few from an
     emulator or device once the app talks to a real server with test
     data), a 512×512 hi-res icon (the in-app adaptive icon in
     `res/mipmap-anydpi-v26` is a vector placeholder — swap it for real
     artwork before this step, and export a matching flat PNG for the Play
     listing itself), and a feature graphic (1024×500) still need real
     assets this doc can't produce for you.
4. **Privacy policy URL** — **required**, and non-optional here specifically:
   this app handles regulated financial-crime PII (customer names, IDs,
   nationalities, transaction data — see the README's licence-boundary and
   design-decisions sections). A drafted policy already exists — see the
   privacy-policy Artifact from the session that set up this repo, or
   regenerate one from the same brief — fill in the bracketed firm details
   (name, contact, deployment URL), publish it somewhere with a stable URL,
   and link it in the listing.
5. **App content questionnaire** (*Policy → App content*): privacy policy
   URL, ads (no), content rating questionnaire (a B2B compliance tool —
   answer accurately; it should rate as suitable for all audiences with no
   mature content), target audience (adults, not designed for children —
   answer "no" to the child-directed questions), government apps /
   financial features declarations as prompted, **Data safety** section (see
   below).
6. **Data safety form** — declare what the app actually does, matching the
   real behavior:
   - Data collected: name, email address (operator accounts), and
     "financial info" / other regulated PII (customer records the firm
     enters) — collected, not shared with third parties, transmitted
     encrypted (HTTPS only — see `network_security_config.xml`), user can
     request deletion via the firm's own MLRO/admin (not an in-app
     self-service flow).
   - Do not declare data as "shared with third parties" unless that's
     actually true for your deployment.
7. **App access** — since every screen requires sign-in, provide a test
   account (email/password) in *App content → App access* so Google's
   reviewers can actually get past the login screen.

## 6. Testing track first

Don't go straight to production. *Release → Testing → Internal testing* (or
Closed testing):
1. Create a release, upload `app-release.aab`.
2. Add release notes.
3. Add testers (their Google account emails, or a Google Group).
4. Roll out to the testing track, share the opt-in link, verify the app
   installs and the golden path works end to end (register org → login →
   screen a name → onboard a customer → triage an alert) against the real
   deployed server from step 1.

## 7. Production rollout

Once testing looks good: *Release → Production* → create a release from the
same (or a newer) AAB → submit for review. First-time app review commonly
takes a few days to a couple of weeks; expect follow-up questions given the
regulated-data nature of the app — the Data safety and App content answers
from step 5 are what reviewers check against.

## 8. Shipping updates

Every subsequent release: bump `versionCode` (must strictly increase) and
`versionName` in `android/app/build.gradle.kts`, rebuild
(`./gradlew bundleRelease -PapiBaseUrl=...`), upload the new AAB to a track,
roll out. Consider a staged rollout percentage for production releases
rather than 100% immediately.
