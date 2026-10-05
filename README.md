# Assist Script Tools

Home Assistant Assist/LLM tools that safely invoke scripts with human-friendly
entity resolution.

## Why

Home Assistant's native intent tools resolve a spoken target such as "Kitchen
Speaker" to a canonical `media_player.*` entity inside Home Assistant. A script
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

1. Select the existing `script.*` entity.
2. In the main configuration form, review the source-derived tool name and
   description, then select a script parameter.
3. Choose **Edit selected parameter** to configure it as **Pass through** or
   **Resolve a target**. Mapped parameters use a human-friendly target; pass-
   through parameters retain the source script behavior.
4. Choose **Edit mappings as JSON** for bulk editing. Updating returns to the
   same main configuration form, where every parameter reflects the JSON state.
5. Choose **Save tool** to create the integration entry.

Each mapping has:
   - `input_name`: the LLM parameter. Name the human concept, such as
     `speaker` or `media_player`, rather than copying an entity-ID-oriented
     source field name such as `media_player_entity_id`. It must contain no
     spaces; use letters, numbers, and underscores.
   - `script_field`: the parameter accepted by the source script.
   - `domains`: allowed target domains.
   - `integrations`: optional allowed integration domains.
   - `multiple`: whether the tool may resolve more than one target.

For a script with a `media_player_entity_id` source field, expose
`media_player` to the LLM:

```json
[
  {
    "input_name": "media_player",
    "script_field": "media_player_entity_id",
    "domains": ["media_player"],
    "integrations": ["music_assistant"],
    "multiple": false
  }
]
```

The LLM sees `media_player`, not `media_player_entity_id`; the latter remains
only the source script field. A call with `"Kitchen
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
included `script.verify_target_resolution`,
`script.verify_music_assistant_target_resolution`, and
`input_boolean.kitchen_speaker` supply safe source scripts and a target for
testing the configuration flow without controlling devices. The Music Assistant
script includes the `media_player` and `music_assistant` entity-selector filter.

Stop the environment with:

```sh
docker compose --profile ui down
```
