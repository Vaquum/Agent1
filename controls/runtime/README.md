# Runtime

Store runtime controls for polling, retries, limits, and mode configuration.

Runtime controls also define active scope boundaries (`active_repositories`) and dev sandbox enforcement (`require_sandbox_scope_for_dev_active`, `sandbox_label`, `sandbox_branch_prefix`).

Runtime scope fields are also used by backend startup guard fencing to reject overlapping `active` scope ownership.
