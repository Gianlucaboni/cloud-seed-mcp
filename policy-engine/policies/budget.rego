# Budget Policy — Cloud Seed MCP
#
# Validates that the estimated monthly cost of all resources in a Terraform
# plan does not exceed the configurable budget limit.
#
# Cost sources (in order of priority):
#   1. Infracost per-resource costs from input.infracost_costs (real pricing)
#   2. Static per-type averages from data.terraform.config.cost_estimates_eur_monthly
#
# The budget limit is data.terraform.config.budget_limit_eur_monthly (default 500 EUR/month).

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
# Infracost costs (from input, injected by Python layer)
# --------------------------------------------------------------------------- #

default infracost_costs := {}

infracost_costs := input.infracost_costs if {
    input.infracost_costs
}

# --------------------------------------------------------------------------- #
# Helper: per-resource cost with Infracost priority
# --------------------------------------------------------------------------- #

# If Infracost provided a cost for this specific resource address, use it.
# Otherwise fall back to the static per-type estimate.
resource_cost(resource) := cost if {
    cost := infracost_costs[resource.address]
} else := cost if {
    cost := object.get(cost_estimates, resource.type, 0)
}

# --------------------------------------------------------------------------- #
# Deny: total estimated monthly cost exceeds budget
# --------------------------------------------------------------------------- #

total_estimated_cost := sum([cost |
    resource := input.resource_changes[_]
    resource.change.actions[_] in {"create", "update"}
    cost := resource_cost(resource)
])

deny contains msg if {
    total_estimated_cost > budget_limit
    msg := sprintf(
        "Budget violation: estimated monthly cost %.2f EUR exceeds limit of %.2f EUR/month. Reduce resources or request a budget increase.",
        [total_estimated_cost, budget_limit]
    )
}

# --------------------------------------------------------------------------- #
# Deny: single resource with extremely high cost (> 50% of budget)
# --------------------------------------------------------------------------- #

deny contains msg if {
    resource := input.resource_changes[_]
    resource.change.actions[_] in {"create", "update"}
    cost := resource_cost(resource)
    cost > budget_limit * 0.5
    msg := sprintf(
        "Budget warning: %s costs %.2f EUR/month (>50%% of %.2f EUR budget)",
        [resource.address, cost, budget_limit]
    )
}
