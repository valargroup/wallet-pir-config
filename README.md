# Wallet PIR configuration

This repository publishes the static trust anchors and dynamic server lists
that wallet applications use for Enhance, Status, Transparent and Receiver PIR.
Rust applications resolve these documents through `zakura-pir-config`, built on
the shared `zakura-service-config` package in wallet-libraries. Voting uses the
same foundation with its own documents, repository and attestation policy.

## Published documents

| Environment | Static document | Dynamic document | Network |
| --- | --- | --- | --- |
| Production | `prod/static-wallet-pir-config.json` | `prod/dynamic-wallet-pir-config.json` | `mainnet` |

The canonical site is `https://valargroup.github.io/wallet-pir-config/`.
GitHub Raw is an additional dynamic-config mirror. Both mirrors are authorized
to supply server lists under the initial `https-transport` policy. HTTPS does
not provide a signed-document freshness or replay guarantee.

The production list advertises `https://wallet-pir.valargroup.dev` as one
base for all four products. This repository publishes production configuration
only; it has no staging or testnet configuration. An empty server list
intentionally causes no private PIR traffic.

**Publish the production entry only after the unified host has been deployed
and qualified.** Its server configuration is prepared in
[wallet-pir #337](https://github.com/valargroup/wallet-pir/pull/337). Before
merging this activation change, verify the four canonical product APIs over
HTTPS, including encrypted queries, and confirm that released wallets can
still use the existing hostnames and paths. Publishing this repository does
not deploy a PIR service.

Each server has one labeled base URL. Clients derive `/enhance/v1`,
`/status/v1`, `/transparent/v1` and `/receiver/v1` beneath it. A wallet explicitly
selects one advertised server. A service failure does not select another server
or fall back to a public lookup. Config mirrors can be tried independently of
that server-selection policy.

## Static pins and authentication

Wallet releases use a static document under
`pins/prod/<sha256>/static-wallet-pir-config.json`, with
`?checksum=sha256:<sha256>` appended to the URL. Its bytes cannot change or
disappear. Current static aliases may change only when their new immutable
copy is included in the same change. The publication command prints the exact
pin URLs; do not copy a checksum from an unverified document.

Static configuration binds a network, dynamic-config mirrors and an
attestation selection. Applications register allowed verification methods in
Rust. A config cannot introduce a method the application did not register.
The initial wallet policy permits `https-transport` with no additional trust
data. Voting's existing round signatures are a separate application policy.

A failed config refresh can retain a wallet's previously accepted config.
Server publications still have their own freshness, chain acceptance, and
payment-validation checks. A server's presence in this list does not prove
complete indexing or authorize wallet funds.

## Updating and publishing

Install the authoritative `wallet-pir-config` verifier from the exact
wallet-libraries revision in `validator-source.json`. It owns schema and
authentication validation; this repository's Python tool owns immutable pins
and publication packaging.

```sh
python3 -m unittest discover -s tests
python3 scripts/config_site.py verify --validator /path/to/wallet-pir-config
python3 scripts/config_site.py build --validator /path/to/wallet-pir-config --output _site
```

The **Print static config pins** workflow prints the production hash-pinned
URL in the `print-pins` job log and its GitHub Actions summary, with a
copy/paste block. It runs on static-pin changes, pushes to `main`, and manual
dispatch. To print the same output locally:

```sh
python3 scripts/config_site.py pins
```

Open a pull request for configuration changes. CI validates production
and every retained production pin against its dynamic document. After a
change merges, the Pages workflow uploads only public configuration, checksum
sidecars, and a manifest identifying the source revision. Source code and local
files are not part of the serving snapshot. GitHub Pages deploys the complete
snapshot as one artifact.

New mirrors, attestation methods, or network identities require a new static
pin. Updating a dynamic list does not require another application release.
If a valid update removes the selected server, the wallet requires an explicit
new selection. Existing notes, keys and wallet history stay in the wallet.
Static trust anchors and dynamic server configuration for wallet PIR clients
