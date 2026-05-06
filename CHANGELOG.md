# Changelog

## 0.1.0

### Breaking changes

- `form_view_router` removed. Consumers replace it with a small project-side
  dispatch (see README's "Views and URLs" section).
- `multistep_form_view` now treats step regions as those whose key starts with
  `STEP_REGION_PREFIX` (`"step_"`). Previously every region except `"success"`
  was walked. The only step-region producer is `AbstractFormStep.region_key`,
  which already emits `step_<identifier>`, so well-behaved consumers see no
  behaviour change. Consumers with non-`step_*` step regions either rename
  them or pass a custom `get_step_regions` callable.

### Features

- `multistep_form_view` accepts `get_step_regions=<callable>` for non-standard
  step layouts.
- `STEP_REGION_PREFIX` exposed at `feincms3_formbuilder.models` as the single
  source of truth for the prefix; used by `AbstractFormStep.region_key`,
  `StepSlugField`, and the walker's default selector.

## 0.0.1

Initial release.
