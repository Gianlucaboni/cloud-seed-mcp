# Resources Policy — Cloud Seed MCP
#
# Validates that every resource in the Terraform plan uses an allowed
# GCP resource type from the whitelist, and blocks GPU instances unless
# an explicit approval flag is present.
#
# Allowed resource types come from data.terraform.config.allowed_resource_types.
# GPU machine type prefixes come from data.terraform.config.gpu_machine_type_prefixes.

package terraform

import future.keywords.in
import future.keywords.if
import future.keywords.contains

# --------------------------------------------------------------------------- #
# Configuration from data/defaults.json
# --------------------------------------------------------------------------- #

default allowed_resource_types := [
    "google_compute_instance",
    "google_compute_network",
    "google_compute_subnetwork",
    "google_compute_firewall",
    "google_storage_bucket",
    "google_bigquery_dataset",
    "google_sql_database_instance",
    "google_cloud_run_service",
    "google_artifact_registry_repository",
    "google_service_account",
    "google_project_service",
    "google_project_iam_member",
    "google_project_iam_binding",
]

allowed_resource_types := data.terraform.config.allowed_resource_types if {
    data.terraform.config.allowed_resource_types
}

default gpu_machine_type_prefixes := ["a2-", "g2-", "a3-"]

gpu_machine_type_prefixes := data.terraform.config.gpu_machine_type_prefixes if {
    data.terraform.config.gpu_machine_type_prefixes
}

default gpu_approval_flag := "cloud_seed_gpu_approved"

gpu_approval_flag := data.terraform.config.gpu_approval_flag if {
    data.terraform.config.gpu_approval_flag
}

# --------------------------------------------------------------------------- #
# Deny: resource type not in the whitelist
# --------------------------------------------------------------------------- #

deny contains msg if {
    resource := input.resource_changes[_]
    resource.change.actions[_] in {"create", "update"}
    not resource.type in allowed_resource_types
    msg := sprintf(
        "Resource type violation: %s uses type '%s' which is not in the allowed resource types whitelist",
        [resource.address, resource.type]
    )
}

# --------------------------------------------------------------------------- #
# Deny: GPU instance via machine type prefix (a2-, g2-, a3-)
# --------------------------------------------------------------------------- #

deny contains msg if {
    resource := input.resource_changes[_]
    resource.type == "google_compute_instance"
    resource.change.actions[_] in {"create", "update"}
    machine_type := resource.change.after.machine_type
    prefix := gpu_machine_type_prefixes[_]
    startswith(machine_type, prefix)
    not has_gpu_approval(resource)
    msg := sprintf(
        "GPU violation: %s uses GPU machine type '%s'. GPU instances require explicit approval (set label '%s' = 'true')",
        [resource.address, machine_type, gpu_approval_flag]
    )
}

# --------------------------------------------------------------------------- #
# Deny: GPU instance via guest_accelerator block
# --------------------------------------------------------------------------- #

deny contains msg if {
    resource := input.resource_changes[_]
    resource.type == "google_compute_instance"
    resource.change.actions[_] in {"create", "update"}
    accelerator := resource.change.after.guest_accelerator[_]
    accelerator.count > 0
    not has_gpu_approval(resource)
    msg := sprintf(
        "GPU violation: %s has guest_accelerator configured. GPU instances require explicit approval (set label '%s' = 'true')",
        [resource.address, gpu_approval_flag]
    )
}

# --------------------------------------------------------------------------- #
# Helper: check if resource has the GPU approval label
# --------------------------------------------------------------------------- #

has_gpu_approval(resource) if {
    labels := resource.change.after.labels
    labels[gpu_approval_flag] == "true"
}
