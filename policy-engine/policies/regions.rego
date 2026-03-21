# Regions Policy — Cloud Seed MCP
#
# Validates that every resource in the Terraform plan uses an allowed
# GCP region or zone. This prevents accidental deployment to regions
# outside of compliance boundaries (e.g., outside Europe).
#
# Allowed values come from data.terraform.config.allowed_regions and
# data.terraform.config.allowed_zones.

package terraform

import future.keywords.in
import future.keywords.if
import future.keywords.contains

# --------------------------------------------------------------------------- #
# Configuration from data/defaults.json
# --------------------------------------------------------------------------- #

default allowed_regions := ["europe-west1", "europe-west4", "europe-west6"]

allowed_regions := data.terraform.config.allowed_regions if {
    data.terraform.config.allowed_regions
}

default allowed_zones := [
    "europe-west1-b", "europe-west1-c", "europe-west1-d",
    "europe-west4-a", "europe-west4-b", "europe-west4-c",
    "europe-west6-a", "europe-west6-b", "europe-west6-c",
]

allowed_zones := data.terraform.config.allowed_zones if {
    data.terraform.config.allowed_zones
}

# --------------------------------------------------------------------------- #
# Deny: resource has a "region" field not in the allowed list
# --------------------------------------------------------------------------- #

deny contains msg if {
    resource := input.resource_changes[_]
    resource.change.actions[_] in {"create", "update"}
    region := resource.change.after.region
    region != null
    not region in allowed_regions
    msg := sprintf(
        "Region violation: %s uses region '%s' which is not in allowed regions %v",
        [resource.address, region, allowed_regions]
    )
}

# --------------------------------------------------------------------------- #
# Deny: resource has a "zone" field not in the allowed list
# --------------------------------------------------------------------------- #

deny contains msg if {
    resource := input.resource_changes[_]
    resource.change.actions[_] in {"create", "update"}
    zone := resource.change.after.zone
    zone != null
    not zone in allowed_zones
    msg := sprintf(
        "Zone violation: %s uses zone '%s' which is not in allowed zones %v",
        [resource.address, zone, allowed_zones]
    )
}

# --------------------------------------------------------------------------- #
# Deny: resource has a "location" field (used by some GCP resources like
# storage buckets and BigQuery datasets) not in the allowed list.
# Allows multi-region values "EU" and "EUR4" as they stay within Europe.
# --------------------------------------------------------------------------- #

eu_multi_regions := {"EU", "EUR4", "eu", "eur4"}

deny contains msg if {
    resource := input.resource_changes[_]
    resource.change.actions[_] in {"create", "update"}
    location := resource.change.after.location
    location != null
    not location in allowed_regions
    not location in eu_multi_regions
    not upper(location) in eu_multi_regions
    msg := sprintf(
        "Location violation: %s uses location '%s' which is not in allowed regions %v or EU multi-regions",
        [resource.address, location, allowed_regions]
    )
}
