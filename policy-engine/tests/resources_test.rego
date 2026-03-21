# Resources Policy Tests — Cloud Seed MCP

package terraform.test.resources

import future.keywords.in
import future.keywords.if
import data.terraform

# --------------------------------------------------------------------------- #
# Test: allowed resource types pass
# --------------------------------------------------------------------------- #

test_allowed_resource_type_passes if {
    result := terraform.deny with input as allowed_type_plan
        with data.terraform.config as config
    type_violations := {msg | msg := result[_]; contains(msg, "Resource type violation")}
    count(type_violations) == 0
}

# --------------------------------------------------------------------------- #
# Test: disallowed resource type is denied
# --------------------------------------------------------------------------- #

test_disallowed_resource_type_denied if {
    result := terraform.deny with input as disallowed_type_plan
        with data.terraform.config as config
    type_violations := {msg | msg := result[_]; contains(msg, "Resource type violation")}
    count(type_violations) > 0
}

# --------------------------------------------------------------------------- #
# Test: GPU machine type (a2-) without approval is denied
# --------------------------------------------------------------------------- #

test_gpu_machine_type_denied if {
    result := terraform.deny with input as gpu_machine_type_plan
        with data.terraform.config as config
    gpu_violations := {msg | msg := result[_]; contains(msg, "GPU violation")}
    count(gpu_violations) > 0
}

# --------------------------------------------------------------------------- #
# Test: guest_accelerator without approval is denied
# --------------------------------------------------------------------------- #

test_guest_accelerator_denied if {
    result := terraform.deny with input as guest_accelerator_plan
        with data.terraform.config as config
    gpu_violations := {msg | msg := result[_]; contains(msg, "GPU violation")}
    count(gpu_violations) > 0
}

# --------------------------------------------------------------------------- #
# Test: GPU instance with approval label passes
# --------------------------------------------------------------------------- #

test_gpu_with_approval_passes if {
    result := terraform.deny with input as gpu_approved_plan
        with data.terraform.config as config
    gpu_violations := {msg | msg := result[_]; contains(msg, "GPU violation")}
    count(gpu_violations) == 0
}

# --------------------------------------------------------------------------- #
# Test: non-GPU compute instance passes
# --------------------------------------------------------------------------- #

test_non_gpu_instance_passes if {
    result := terraform.deny with input as non_gpu_plan
        with data.terraform.config as config
    gpu_violations := {msg | msg := result[_]; contains(msg, "GPU violation")}
    count(gpu_violations) == 0
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
        "google_bigquery_dataset", "google_bigquery_table",
        "google_service_account", "google_project_service",
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

allowed_type_plan := {
    "resource_changes": [
        {
            "address": "google_compute_instance.web",
            "type": "google_compute_instance",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-web",
                    "machine_type": "e2-medium",
                    "zone": "europe-west1-b",
                    "labels": {},
                    "guest_accelerator": []
                }
            }
        },
        {
            "address": "google_storage_bucket.data",
            "type": "google_storage_bucket",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-data",
                    "location": "europe-west1",
                    "encryption": [{"default_kms_key_name": "key"}]
                }
            }
        }
    ]
}

disallowed_type_plan := {
    "resource_changes": [
        {
            "address": "google_container_cluster.gke",
            "type": "google_container_cluster",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-gke-cluster",
                    "location": "europe-west1"
                }
            }
        }
    ]
}

gpu_machine_type_plan := {
    "resource_changes": [
        {
            "address": "google_compute_instance.gpu_vm",
            "type": "google_compute_instance",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-gpu-vm",
                    "machine_type": "a2-highgpu-1g",
                    "zone": "europe-west4-a",
                    "labels": {},
                    "guest_accelerator": []
                }
            }
        }
    ]
}

guest_accelerator_plan := {
    "resource_changes": [
        {
            "address": "google_compute_instance.accel_vm",
            "type": "google_compute_instance",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-accel-vm",
                    "machine_type": "n1-standard-4",
                    "zone": "europe-west4-b",
                    "labels": {},
                    "guest_accelerator": [
                        {"type": "nvidia-tesla-t4", "count": 1}
                    ]
                }
            }
        }
    ]
}

gpu_approved_plan := {
    "resource_changes": [
        {
            "address": "google_compute_instance.gpu_ok",
            "type": "google_compute_instance",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-gpu-ok",
                    "machine_type": "a2-highgpu-1g",
                    "zone": "europe-west4-a",
                    "labels": {
                        "cloud_seed_gpu_approved": "true",
                        "team": "ml"
                    },
                    "guest_accelerator": []
                }
            }
        }
    ]
}

non_gpu_plan := {
    "resource_changes": [
        {
            "address": "google_compute_instance.standard_vm",
            "type": "google_compute_instance",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-standard-vm",
                    "machine_type": "e2-medium",
                    "zone": "europe-west1-b",
                    "labels": {},
                    "guest_accelerator": []
                }
            }
        }
    ]
}
