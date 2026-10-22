# Updating wallet PIR configuration

Open a pull request against `main` with a title describing the client-visible
change. This repository publishes production configuration only. Add a server
only after its four product routes have been verified over HTTPS.

Validate documents with the Rust verifier pinned by `validator-source.json`,
then run the publication tests and verification command in the README.
Include a new content-addressed copy whenever a current static alias changes.
Previously published production static pin files must remain byte-for-byte intact.

Configuration changes do not authorize service deployment, a wallet release,
or an automatic change to a user's selected server.
