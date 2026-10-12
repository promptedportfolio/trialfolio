# Store your credentials

A backtest or an experiment sends requests to Portfolio123 with your API ID and key. This page shows how to give them to Trial Folio without leaving the key in a file or your shell's history.

The demo, a plan's review, `trialfolio report`, and `trialfolio review` need no credentials.

## Before you start

- **Your API ID and key.** Portfolio123's website lists both under DataMiner & API.
- **What Trial Folio reads.** It reads them from two environment variables, and never from a file. It never saves or logs them.

    | Variable | Contents |
    |---|---|
    | `TRIALFOLIO_P123_API_ID` | Your Portfolio123 API ID |
    | `TRIALFOLIO_P123_API_KEY` | Your Portfolio123 API key |

- **Where it sends them.** Only to Portfolio123's API, directly. It ignores proxy settings and `.netrc`, and if `SSLKEYLOGFILE` is set, `trialfolio run` warns and ignores it. [Credentials](https://github.com/promptedportfolio/trialfolio/blob/main/docs/contracts.md#credentials) gives the rules.

!!! warning "Keep the key out of files and history"
    Keep the key out of your shell's history, and out of any plain-text file. Don't put it in a `.env` file in your workspace: Trial Folio doesn't read one, and the file would sit beside the runs and reports you might copy, zip, or share.

Choose one of these ways:

- [In the macOS keychain](#in-the-macos-keychain), entered once
- [In a Linux keyring](#in-a-linux-keyring), entered once
- [Through your password manager](#through-your-password-manager)
- [At a prompt, for one shell session](#at-a-prompt-for-one-shell-session)

## In the macOS keychain

1. Store the ID and the key in your login keychain. Each command asks for the value twice, at a prompt that doesn't show it:

    ```sh
    security add-generic-password -s trialfolio -a p123-api-id -w
    security add-generic-password -s trialfolio -a p123-api-key -w
    ```

2. In your shell's startup file, such as `~/.zshrc`, replace the `alias trialfolio=...` line from [setting up](../tutorials/first-backtest.md) with this function. For each command, it reads both values from the keychain and sets them for that command alone, so your shell doesn't keep them. As for the alias, replace the path with the repository's:

    ```sh
    trialfolio() {
      TRIALFOLIO_P123_API_ID="$(security find-generic-password -s trialfolio -a p123-api-id -w)" \
      TRIALFOLIO_P123_API_KEY="$(security find-generic-password -s trialfolio -a p123-api-key -w)" \
        uv run --project ~/trialfolio trialfolio "$@"
    }
    ```

3. Open a new terminal, so the function replaces the alias.

**To change the key,** run this. `-U` updates the item:

```sh
security add-generic-password -U -s trialfolio -a p123-api-key -w
```

**To remove both,** run this, and the same with `p123-api-key`:

```sh
security delete-generic-password -s trialfolio -a p123-api-id
```

## In a Linux keyring

A keyring that serves the Secret Service, such as GNOME Keyring, works the same way as the macOS keychain, through `secret-tool`. Trial Folio hasn't been tested on Linux yet.

1. Store the key. This command asks for it:

    ```sh
    secret-tool store --label='Trial Folio API key' service trialfolio account p123-api-key
    ```

    Store the ID the same way, with `account p123-api-id`.

2. Write the function of [the macOS keychain's step 2](#in-the-macos-keychain), reading each value with `secret-tool lookup` in place of `security find-generic-password ... -w`. This reads the key:

    ```sh
    secret-tool lookup service trialfolio account p123-api-key
    ```

3. Open a new terminal, so the function replaces the alias.

## Through your password manager

Many password managers have a command-line tool that runs one command with secrets set as environment variables. It reads them from a file of references, which name where each secret is kept and never hold the secret itself.

1. Write references for the two variables in such a file in your workspace, with a name such as `.env` or `.env.local`. The workspace's `.gitignore` keeps it out of Git.
2. Run each `trialfolio` command through the tool, as its documentation describes. The tool starts the command itself, without your shell's aliases, so give it the command the `trialfolio` alias stands for, with the repository's path, such as:

    ```sh
    uv run --project ~/trialfolio trialfolio run screen.yaml --out runs/first/
    ```

## At a prompt, for one shell session

1. Type each value at a prompt. The second doesn't show the key:

    ```sh
    read -r TRIALFOLIO_P123_API_ID
    read -rs TRIALFOLIO_P123_API_KEY
    export TRIALFOLIO_P123_API_ID TRIALFOLIO_P123_API_KEY
    ```

2. Run your `trialfolio` commands in the same terminal. The values last until you close it. This removes them sooner:

    ```sh
    unset TRIALFOLIO_P123_API_ID TRIALFOLIO_P123_API_KEY
    ```

## Check

- With the keychain, this prints `p123-api-id found` and `p123-api-key found`. It checks that both items are there, without printing either value:

    ```sh
    for item in p123-api-id p123-api-key; do
      security find-generic-password -s trialfolio -a "$item" >/dev/null && echo "$item found"
    done
    ```

    If a line is missing, store that item again, as in [the keychain's step 1](#in-the-macos-keychain).

- With the keychain function, `type trialfolio` says it's a shell function, and `[ -z "$TRIALFOLIO_P123_API_KEY" ] && echo unset` prints `unset`: your shell doesn't keep the key.
- No command in your shell's history file set the key by name: `grep -c 'TRIALFOLIO_P123_API_KEY[=]' "$HISTFILE"` prints 0. The brackets keep the check from counting itself. It finds only commands such as `TRIALFOLIO_P123_API_KEY=...`, not a key typed or pasted any other way.
- Without the variables, an approved plan fails with `provider.auth_failed`, exit code 5. The message names the missing variables, and says nothing was sent and no output was created.
