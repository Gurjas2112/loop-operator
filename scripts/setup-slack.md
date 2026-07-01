# Slack setup (not bundled — connector accounts are org runtime state)

Loop uses Slack two ways off one account: the **`desk` surface** (people DM the bot) and the
**`notify_owners` connector call** (the operator DMs owners). Do this once.

## 1. Create the Slack app (Socket Mode)
1. Go to https://api.slack.com/apps -> **Create New App** -> From scratch.
2. **Socket Mode** -> enable (this is what lets it work locally with no public webhook URL).
3. **OAuth & Permissions** -> Bot Token Scopes: `chat:write`, `channels:read`, `app_mentions:read`,
   `im:history`, `im:write`.
4. **Event Subscriptions** -> enable; subscribe to bot events `message.im`, `app_mention`.
5. Install to your workspace. Collect the **Bot token** (`xoxb-...`) and the **App-level token**
   (`xapp-...`, create under Basic Information -> App-Level Tokens with `connections:write`).

## 2. Wire the connector in Lemma
```bash
lemma connectors overview                                  # see installed auth configs
lemma connectors auth-configs create slack --name workspace-slack   # provider LEMMA (default)
# Connect the account with your tokens (token-style account):
lemma connectors accounts create --auth-config workspace-slack --file account.json
#   account.json: {"bot_token":"xoxb-...","app_token":"xapp-..."}  (confirm exact keys via:)
#   lemma connectors auth-configs get workspace-slack
lemma connectors accounts list --app slack                 # note the <account-id>
```

## 3. Confirm the operation id used by notify_owners
```bash
lemma connectors operations search workspace-slack "post message"
#   If the id differs from "chat_post_message", update SLACK_POST_OP in
#   loop/functions/notify_owners/code.py and re-import that function.
```

## 4. Point the surface at the account
```bash
# Edit loop/surfaces/slack/slack.json: set account_id + a real channel id, then:
lemma pods import ./loop/surfaces/slack
lemma surfaces setup slack        # paste back any webhook/redirect URL it prints
lemma surfaces get slack          # expect status ACTIVE
```

## 5. Map yourself
In `seed/seed.sh` (or directly), set `user_prefs.slack_user_id` to your Slack **member id**
(profile -> More -> Copy member ID, `U...`).

## Verify
DM the bot "what's due today" -> `desk` replies with the seeded queue.
