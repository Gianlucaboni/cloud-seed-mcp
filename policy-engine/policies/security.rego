# Security Policy — Cloud Seed MCP
#
# Validates security requirements for GCP resources:
# - Storage buckets must have encryption configuration
# - No resources may grant public access (allUsers / allAuthenticatedUsers)
# - Resource names must follow naming convention (lowercase, hyphens, project prefix)

package terraform

import future.keywords.in
import future.keywords.if
import future.keywords.contains

# --------------------------------------------------------------------------- #
# Configuration from data/defaults.json
# --------------------------------------------------------------------------- #

default public_access_members := ["allUsers", "allAuthenticatedUsers"]

public_access_members := data.terraform.config.public_access_members if {
    data.terraform.config.public_access_members
}

default naming_pattern := "^[a-z][a-z0-9-]*$"

naming_pattern := data.terraform.config.naming_pattern if {
    data.terraform.config.naming_pattern
}

# --------------------------------------------------------------------------- #
# Deny: storage bucket without encryption configuration
# --------------------------------------------------------------------------- #

deny contains msg if {
    resource := input.resource_changes[_]
    resource.type == "google_storage_bucket"
    resource.change.actions[_] in {"create", "update"}
    not has_encryption(resource)
    msg := sprintf(
        "Security violation: %s — storage bucket must have encryption configuration (CMEK or default encryption block)",
        [resource.address]
    )
}

has_encryption(resource) if {
    encryption := resource.change.after.encryption
    encryption != null
    count(encryption) > 0
}

# --------------------------------------------------------------------------- #
# Deny: IAM member/binding grants public access (allUsers / allAuthenticatedUsers)
# --------------------------------------------------------------------------- #

# Check google_storage_bucket_iam_member
deny contains msg if {
    resource := input.resource_changes[_]
    resource.type == "google_storage_bucket_iam_member"
    resource.change.actions[_] in {"create", "update"}
    member := resource.change.after.member
    member in public_access_members
    msg := sprintf(
        "Security violation: %s grants public access via member '%s'. Public access is not allowed.",
        [resource.address, member]
    )
}

# Check google_storage_bucket_iam_binding members list
deny contains msg if {
    resource := input.resource_changes[_]
    resource.type == "google_storage_bucket_iam_binding"
    resource.change.actions[_] in {"create", "update"}
    member := resource.change.after.members[_]
    member in public_access_members
    msg := sprintf(
        "Security violation: %s grants public access via member '%s'. Public access is not allowed.",
        [resource.address, member]
    )
}

# Check google_project_iam_member
deny contains msg if {
    resource := input.resource_changes[_]
    resource.type == "google_project_iam_member"
    resource.change.actions[_] in {"create", "update"}
    member := resource.change.after.member
    member in public_access_members
    msg := sprintf(
        "Security violation: %s grants public project access via member '%s'. Public access is not allowed.",
        [resource.address, member]
    )
}

# Check google_project_iam_binding members list
deny contains msg if {
    resource := input.resource_changes[_]
    resource.type == "google_project_iam_binding"
    resource.change.actions[_] in {"create", "update"}
    member := resource.change.after.members[_]
    member in public_access_members
    msg := sprintf(
        "Security violation: %s grants public project access via member '%s'. Public access is not allowed.",
        [resource.address, member]
    )
}

# Check google_cloud_run_service_iam_member
deny contains msg if {
    resource := input.resource_changes[_]
    resource.type == "google_cloud_run_service_iam_member"
    resource.change.actions[_] in {"create", "update"}
    member := resource.change.after.member
    member in public_access_members
    msg := sprintf(
        "Security violation: %s grants public Cloud Run access via member '%s'. Public access is not allowed.",
        [resource.address, member]
    )
}

# Check google_cloud_run_service_iam_binding members list
deny contains msg if {
    resource := input.resource_changes[_]
    resource.type == "google_cloud_run_service_iam_binding"
    resource.change.actions[_] in {"create", "update"}
    member := resource.change.after.members[_]
    member in public_access_members
    msg := sprintf(
        "Security violation: %s grants public Cloud Run access via member '%s'. Public access is not allowed.",
        [resource.address, member]
    )
}

# --------------------------------------------------------------------------- #
# Deny: resource name does not follow naming convention
# --------------------------------------------------------------------------- #

deny contains msg if {
    resource := input.resource_changes[_]
    resource.change.actions[_] in {"create", "update"}
    name := resource.change.after.name
    name != null
    not regex.match(naming_pattern, name)
    msg := sprintf(
        "Naming violation: %s has name '%s' which does not match the required pattern '%s' (lowercase letters, numbers, and hyphens only, must start with a letter)",
        [resource.address, name, naming_pattern]
    )
}
