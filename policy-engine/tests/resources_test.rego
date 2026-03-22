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
# Test: data pipeline resource types pass (walkthrough scenario)
# --------------------------------------------------------------------------- #

test_data_pipeline_resources_pass if {
    result := terraform.deny with input as data_pipeline_plan
        with data.terraform.config as config
    type_violations := {msg | msg := result[_]; contains(msg, "Resource type violation")}
    count(type_violations) == 0
}

# --------------------------------------------------------------------------- #
# Test configuration
# --------------------------------------------------------------------------- #

config := {
    "budget_limit_eur_monthly": 500,
    "allowed_regions": ["europe-west1", "europe-west4", "europe-west6"],
    "allowed_zones": ["europe-west1-b", "europe-west1-c", "europe-west1-d", "europe-west4-a", "europe-west4-b", "europe-west4-c", "europe-west6-a", "europe-west6-b", "europe-west6-c"],
    "allowed_resource_types": [
        "google_compute_instance", "google_compute_network", "google_compute_subnetwork",
        "google_compute_firewall", "google_compute_address",
        "google_compute_router", "google_compute_router_nat",
        "google_storage_bucket", "google_storage_bucket_iam_member", "google_storage_bucket_iam_binding",
        "google_bigquery_dataset", "google_bigquery_table", "google_bigquery_data_transfer_config",
        "google_sql_database_instance", "google_sql_database", "google_sql_user",
        "google_cloud_run_service", "google_cloud_run_service_iam_member", "google_cloud_run_service_iam_binding",
        "google_artifact_registry_repository",
        "google_service_account", "google_service_account_iam_member", "google_service_account_iam_binding",
        "google_project_iam_member", "google_project_iam_binding", "google_project_service",
        "google_secret_manager_secret", "google_secret_manager_secret_version",
        "google_pubsub_topic", "google_pubsub_subscription",
        "google_cloudfunctions2_function", "google_cloud_scheduler_job",
        "google_vpc_access_connector",
        "google_iam_workload_identity_pool", "google_iam_workload_identity_pool_provider",
        "google_firestore_database", "google_dns_managed_zone", "google_dns_record_set"
    ],
    "cost_estimates_eur_monthly": {
        "google_compute_instance": 25.0,
        "google_storage_bucket": 2.0,
        "google_bigquery_table": 5.0,
        "google_sql_database_instance": 50.0,
        "google_cloudfunctions2_function": 10.0,
        "google_cloud_scheduler_job": 0.1
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

data_pipeline_plan := {
    "resource_changes": [
        {
            "address": "google_bigquery_dataset.api_data",
            "type": "google_bigquery_dataset",
            "change": {
                "actions": ["create"],
                "after": {
                    "dataset_id": "api-data",
                    "location": "EU"
                }
            }
        },
        {
            "address": "google_bigquery_table.daily_records",
            "type": "google_bigquery_table",
            "change": {
                "actions": ["create"],
                "after": {
                    "table_id": "daily-records",
                    "dataset_id": "api-data"
                }
            }
        },
        {
            "address": "google_storage_bucket.csv_landing",
            "type": "google_storage_bucket",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-csv-landing",
                    "location": "europe-west1",
                    "encryption": [{"default_kms_key_name": "key"}]
                }
            }
        },
        {
            "address": "google_cloudfunctions2_function.api_fetcher",
            "type": "google_cloudfunctions2_function",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-api-fetcher",
                    "location": "europe-west1"
                }
            }
        },
        {
            "address": "google_cloud_scheduler_job.daily_trigger",
            "type": "google_cloud_scheduler_job",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-daily-trigger",
                    "region": "europe-west1"
                }
            }
        },
        {
            "address": "google_bigquery_data_transfer_config.csv_sync",
            "type": "google_bigquery_data_transfer_config",
            "change": {
                "actions": ["create"],
                "after": {
                    "display_name": "acme-csv-sync",
                    "location": "EU"
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
