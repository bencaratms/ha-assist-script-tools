# Assist Script Tools

Home Assistant Assist/LLM tools that safely invoke scripts with human-friendly
entity resolution.

## Why

Home Assistant's native intent tools resolve a spoken target such as "Kitchen
Nabu" to a canonical `media_player.*` entity inside Home Assistant. A script
exposed directly to Assist instead receives the model's arguments as-is, which
can cause an LLM to guess an entity ID.

This integration wraps an existing script in an Assist-only tool. For every
configured resolved field, it uses Home Assistant Core's target matcher against
entities exposed to the active Assist assistant. It rejects zero or ambiguous
matches and calls the source script only after replacing the friendly target
with the matched canonical entity ID.

## Installation with HACS

1. In HACS, select the three-dot menu in the upper-right corner, then choose
   **Custom repositories**.
2. Add `https://github.com/bencaratms/ha-assist-script-tools`, select
   **Integration** as the category, and select **Add**.
3. Find **Assist Script Tools** in HACS, select **Download**, then restart
   Home Assistant.
4. In **Settings** > **Devices & services**, select **Add integration** and
   search for **Assist Script Tools**.

## Configuration

Create one integration entry for each script to expose:

1. Select the existing `script.*` entity, then provide a concise tool name and
   description.
2. Select **Add a resolved field** for each script parameter that needs
   human-friendly entity resolution. The form populates its script-field options
   from the selected script and its domain options from your existing entities.
3. Select **Edit mappings as JSON** for bulk editing. Saving the JSON replaces
   the same mappings shown in the guided form, so you can switch between either
   view without losing changes.

Each mapping has:
   - `input_name`: the human-friendly LLM parameter.
   - `script_field`: the parameter accepted by the source script.
   - `domains`: allowed target domains.
   - `multiple`: whether the tool may resolve more than one target.

For a script accepting `media_player_entity_id`, use:

```json
[
  {
    "input_name": "speaker",
    "script_field": "media_player_entity_id",
    "domains": ["media_player"],
    "multiple": false
  }
]
```

The LLM sees `speaker`, not `media_player_entity_id`; a call with `"Kitchen
Speaker"` is resolved by Home Assistant before the script receives
`media_player.kitchen_speaker`.

Disable the source script's own Assist exposure so the model cannot choose the
unsafe raw-ID tool instead of the wrapper.

## Development

Run the isolated Home Assistant test suite with Docker:

```sh
docker compose run --build --rm test
```

### Manual Home Assistant UI testing

Run a local Home Assistant instance with the custom component mounted from this
repository:

```sh
docker compose --profile ui up -d homeassistant
```

Open `http://localhost:8123`, complete Home Assistant's local onboarding, then
add **Assist Script Tools** from **Settings** > **Devices & services**. The
included `script.verify_target_resolution` supplies a safe source script for
testing the configuration flow without controlling media.

Stop the environment with:

```sh
docker compose --profile ui down
```
