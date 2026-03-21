# Budget Policy — Cloud Seed MCP
#
# Validates that the estimated monthly cost of all resources in a Terraform
# plan does not exceed the configurable budget limit.
#
# Cost estimates are approximate per-resource-type averages stored in
# data.terraform.config.cost_estimates_eur_monthly. The budget limit is
# data.terraform.config.budget_limit_eur_monthly (default 500 EUR/month).

package terraform

import future.keywords.in
import future.keywords.if
import future.keywords.contains

# --------------------------------------------------------------------------- #
# Configuration from data/defaults.json
# --------------------------------------------------------------------------- #

default budget_limit := 500

budget_limit := data.terraform.config.budget_limit_eur_monthly if {
    data.terraform.config.budget_limit_eur_monthly
}

default cost_estimates := {}

cost_estimates := data.terraform.config.cost_estimates_eur_monthly if {
    data.terraform.config.cost_estimates_eur_monthly
}

# --------------------------------------------------------------------------- #
# Deny: total estimated monthly cost exceeds budget
# --------------------------------------------------------------------------- #

total_estimated_cost := sum([cost |
    resource := input.resource_changes[_]
    resource.change.actions[_] in {"create", "update"}
    cost := object.get(cost_estimates, resource.type, 0)
])

deny contains msg if {
    total_estimated_cost > budget_limit
    msg := sprintf(
        "Budget violation: estimated monthly cost %.2f EUR exceeds limit of %.2f EUR/month. Reduce resources or request a budget increase.",
        [total_estimated_cost, budget_limit]
    )
}

# --------------------------------------------------------------------------- #
# Deny: single resource type with extremely high cost (> 50% of budget)
# --------------------------------------------------------------------------- #

deny contains msg if {
    resource := input.resource_changes[_]
    resource.change.actions[_] in {"create", "update"}
    cost := object.get(cost_estimates, resource.type, 0)
    cost > budget_limit * 0.5
    msg := sprintf(
        "Budget warning: %s — resource type %s alone costs %.2f EUR/month (>50%% of %.2f EUR budget)",
        [resource.address, resource.type, cost, budget_limit]
    )
}
