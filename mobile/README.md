# Revue Mobile

This is the first iOS and Android app shell for Revue. It is built with Expo React Native so one codebase can run on both platforms.

The current app opens the real Revue website inside the app, so it uses the exact same account, data, feed, profile, notifications, comments, likes, saves, and recommendations as `revue.social`. There is no separate dummy mobile database.

## Run locally

```powershell
cd "C:\Review App\mobile"
npm.cmd install
npm.cmd run start -- --clear
```

Then open the Expo QR code in Expo Go, or press `i` for iOS simulator and `a` for Android emulator.

## Connect to the API

By default the app reads from:

```text
https://www.revue.social
```

For local Django development, set:

```powershell
$env:EXPO_PUBLIC_REVUE_API_URL="http://YOUR-LAN-IP:8000"
npm.cmd run start -- --clear
```

Use your computer's LAN IP instead of `127.0.0.1` when testing on a real phone.

## Current mobile scope

- Real Revue website inside the app
- Shared cookies for login persistence
- Pull to refresh
- Native loading and error states

## Next mobile milestones

- App icon and splash screen
- TestFlight and Google Play internal builds
- Native push notifications
- Gradual native replacement of individual screens once the API is complete

## Expo Go compatibility

This project is pinned to Expo SDK 54 so it can run on the current App Store / Play Store Expo Go runtime.

If Expo still says the project is incompatible, reset installed packages:

```powershell
cd "C:\Review App\mobile"
Ctrl+C
Remove-Item -Recurse -Force node_modules, package-lock.json
npm.cmd install
npm.cmd run start -- --clear
```
