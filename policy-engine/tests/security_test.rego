# Security Policy Tests — Cloud Seed MCP

package terraform.test.security

import future.keywords.in
import future.keywords.if
import data.terraform

# --------------------------------------------------------------------------- #
# Test: encrypted bucket passes
# --------------------------------------------------------------------------- #

test_encrypted_bucket_passes if {
    result := terraform.deny with input as encrypted_bucket_plan
        with data.terraform.config as config
    encryption_violations := {msg | msg := result[_]; contains(msg, "encryption")}
    count(encryption_violations) == 0
}

# --------------------------------------------------------------------------- #
# Test: unencrypted bucket is denied
# --------------------------------------------------------------------------- #

test_unencrypted_bucket_denied if {
    result := terraform.deny with input as unencrypted_bucket_plan
        with data.terraform.config as config
    encryption_violations := {msg | msg := result[_]; contains(msg, "encryption")}
    count(encryption_violations) > 0
}

# --------------------------------------------------------------------------- #
# Test: bucket with null encryption is denied
# --------------------------------------------------------------------------- #

test_null_encryption_denied if {
    result := terraform.deny with input as null_encryption_plan
        with data.terraform.config as config
    encryption_violations := {msg | msg := result[_]; contains(msg, "encryption")}
    count(encryption_violations) > 0
}

# --------------------------------------------------------------------------- #
# Test: public bucket IAM member is denied
# --------------------------------------------------------------------------- #

test_public_iam_member_denied if {
    result := terraform.deny with input as public_iam_member_plan
        with data.terraform.config as config
    public_violations := {msg | msg := result[_]; contains(msg, "public access")}
    count(public_violations) > 0
}

# --------------------------------------------------------------------------- #
# Test: public bucket IAM binding is denied
# --------------------------------------------------------------------------- #

test_public_iam_binding_denied if {
    result := terraform.deny with input as public_iam_binding_plan
        with data.terraform.config as config
    public_violations := {msg | msg := result[_]; contains(msg, "public access")}
    count(public_violations) > 0
}

# --------------------------------------------------------------------------- #
# Test: private IAM member passes
# --------------------------------------------------------------------------- #

test_private_iam_member_passes if {
    result := terraform.deny with input as private_iam_member_plan
        with data.terraform.config as config
    public_violations := {msg | msg := result[_]; contains(msg, "public access")}
    count(public_violations) == 0
}

# --------------------------------------------------------------------------- #
# Test: resource with valid name passes
# --------------------------------------------------------------------------- #

test_valid_name_passes if {
    result := terraform.deny with input as valid_name_plan
        with data.terraform.config as config
    naming_violations := {msg | msg := result[_]; contains(msg, "Naming violation")}
    count(naming_violations) == 0
}

# --------------------------------------------------------------------------- #
# Test: resource with invalid name (uppercase, underscores) is denied
# --------------------------------------------------------------------------- #

test_invalid_name_denied if {
    result := terraform.deny with input as invalid_name_plan
        with data.terraform.config as config
    naming_violations := {msg | msg := result[_]; contains(msg, "Naming violation")}
    count(naming_violations) > 0
}

# --------------------------------------------------------------------------- #
# Test: public Cloud Run IAM is denied
# --------------------------------------------------------------------------- #

test_public_cloud_run_denied if {
    result := terraform.deny with input as public_cloud_run_plan
        with data.terraform.config as config
    public_violations := {msg | msg := result[_]; contains(msg, "public")}
    count(public_violations) > 0
}

# --------------------------------------------------------------------------- #
# Test configuration
# --------------------------------------------------------------------------- #

config := {
    "budget_limit_eur_monthly": 500,
    "allowed_regions": ["europe-west1", "europe-west4", "europe-west6"],
    "allowed_zones": ["europe-west1-b", "europe-west1-c", "europe-west1-d", "europe-west4-a", "europe-west4-b", "europe-west4-c", "europe-west6-a", "europe-west6-b", "europe-west6-c"],
    "allowed_resource_types": [
        "google_compute_instance", "google_storage_bucket", "google_cloud_run_service",
        "google_artifact_registry_repository", "google_sql_database_instance",
        "google_bigquery_dataset", "google_service_account", "google_project_service",
        "google_compute_network", "google_compute_subnetwork",
        "google_storage_bucket_iam_member", "google_storage_bucket_iam_binding",
        "google_project_iam_member", "google_project_iam_binding",
        "google_cloud_run_service_iam_member", "google_cloud_run_service_iam_binding"
    ],
    "cost_estimates_eur_monthly": {
        "google_compute_instance": 25.0,
        "google_storage_bucket": 2.0,
        "google_sql_database_instance": 50.0
    },
    "gpu_machine_type_prefixes": ["a2-", "g2-", "a3-"],
    "gpu_approval_flag": "cloud_seed_gpu_approved",
    "naming_pattern": "^[a-z][a-z0-9-]*$",
    "public_access_members": ["allUsers", "allAuthenticatedUsers"]
}

# --------------------------------------------------------------------------- #
# Test fixtures
# --------------------------------------------------------------------------- #

encrypted_bucket_plan := {
    "resource_changes": [
        {
            "address": "google_storage_bucket.encrypted",
            "type": "google_storage_bucket",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-encrypted-bucket",
                    "location": "europe-west1",
                    "encryption": [
                        {"default_kms_key_name": "projects/acme/locations/europe-west1/keyRings/main/cryptoKeys/key"}
                    ]
                }
            }
        }
    ]
}

unencrypted_bucket_plan := {
    "resource_changes": [
        {
            "address": "google_storage_bucket.unencrypted",
            "type": "google_storage_bucket",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-unencrypted-bucket",
                    "location": "europe-west1",
                    "encryption": []
                }
            }
        }
    ]
}

null_encryption_plan := {
    "resource_changes": [
        {
            "address": "google_storage_bucket.null_enc",
            "type": "google_storage_bucket",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-null-enc-bucket",
                    "location": "europe-west1",
                    "encryption": null
                }
            }
        }
    ]
}

public_iam_member_plan := {
    "resource_changes": [
        {
            "address": "google_storage_bucket_iam_member.public",
            "type": "google_storage_bucket_iam_member",
            "change": {
                "actions": ["create"],
                "after": {
                    "bucket": "acme-bucket",
                    "role": "roles/storage.objectViewer",
                    "member": "allUsers"
                }
            }
        }
    ]
}

public_iam_binding_plan := {
    "resource_changes": [
        {
            "address": "google_storage_bucket_iam_binding.public",
            "type": "google_storage_bucket_iam_binding",
            "change": {
                "actions": ["create"],
                "after": {
                    "bucket": "acme-bucket",
                    "role": "roles/storage.objectViewer",
                    "members": [
                        "serviceAccount:sa@project.iam.gserviceaccount.com",
                        "allAuthenticatedUsers"
                    ]
                }
            }
        }
    ]
}

private_iam_member_plan := {
    "resource_changes": [
        {
            "address": "google_storage_bucket_iam_member.private",
            "type": "google_storage_bucket_iam_member",
            "change": {
                "actions": ["create"],
                "after": {
                    "bucket": "acme-bucket",
                    "role": "roles/storage.objectViewer",
                    "member": "serviceAccount:sa@project.iam.gserviceaccount.com"
                }
            }
        }
    ]
}

valid_name_plan := {
    "resource_changes": [
        {
            "address": "google_compute_instance.valid",
            "type": "google_compute_instance",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-web-server-01",
                    "machine_type": "e2-medium",
                    "zone": "europe-west1-b",
                    "labels": {},
                    "guest_accelerator": []
                }
            }
        }
    ]
}

invalid_name_plan := {
    "resource_changes": [
        {
            "address": "google_compute_instance.bad_name",
            "type": "google_compute_instance",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "Acme_BAD_Name",
                    "machine_type": "e2-medium",
                    "zone": "europe-west1-b",
                    "labels": {},
                    "guest_accelerator": []
                }
            }
        }
    ]
}

public_cloud_run_plan := {
    "resource_changes": [
        {
            "address": "google_cloud_run_service_iam_member.public",
            "type": "google_cloud_run_service_iam_member",
            "change": {
                "actions": ["create"],
                "after": {
                    "service": "acme-api",
                    "role": "roles/run.invoker",
                    "member": "allUsers"
                }
            }
        }
    ]
}
