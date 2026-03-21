# Regions Policy Tests — Cloud Seed MCP

package terraform.test.regions

import future.keywords.in
import future.keywords.if
import data.terraform

# --------------------------------------------------------------------------- #
# Test: resources in allowed European regions pass
# --------------------------------------------------------------------------- #

test_allowed_region_passes if {
    result := terraform.deny with input as eu_region_plan
        with data.terraform.config as config
    region_violations := {msg | msg := result[_]; contains(msg, "Region violation")}
    zone_violations := {msg | msg := result[_]; contains(msg, "Zone violation")}
    location_violations := {msg | msg := result[_]; contains(msg, "Location violation")}
    count(region_violations) == 0
    count(zone_violations) == 0
    count(location_violations) == 0
}

# --------------------------------------------------------------------------- #
# Test: VM in us-central1-a is denied (zone violation)
# --------------------------------------------------------------------------- #

test_us_central_zone_denied if {
    result := terraform.deny with input as us_zone_plan
        with data.terraform.config as config
    zone_violations := {msg | msg := result[_]; contains(msg, "Zone violation")}
    count(zone_violations) > 0
}

# --------------------------------------------------------------------------- #
# Test: resource with us-central1 region is denied
# --------------------------------------------------------------------------- #

test_us_central_region_denied if {
    result := terraform.deny with input as us_region_plan
        with data.terraform.config as config
    region_violations := {msg | msg := result[_]; contains(msg, "Region violation")}
    count(region_violations) > 0
}

# --------------------------------------------------------------------------- #
# Test: bucket with US location is denied
# --------------------------------------------------------------------------- #

test_us_location_denied if {
    result := terraform.deny with input as us_location_plan
        with data.terraform.config as config
    location_violations := {msg | msg := result[_]; contains(msg, "Location violation")}
    count(location_violations) > 0
}

# --------------------------------------------------------------------------- #
# Test: EU multi-region location is allowed
# --------------------------------------------------------------------------- #

test_eu_multi_region_allowed if {
    result := terraform.deny with input as eu_multi_region_plan
        with data.terraform.config as config
    location_violations := {msg | msg := result[_]; contains(msg, "Location violation")}
    count(location_violations) == 0
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
        "google_compute_network", "google_compute_subnetwork"
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

eu_region_plan := {
    "resource_changes": [
        {
            "address": "google_compute_instance.eu_vm",
            "type": "google_compute_instance",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-eu-vm",
                    "machine_type": "e2-medium",
                    "zone": "europe-west1-b",
                    "labels": {},
                    "guest_accelerator": []
                }
            }
        },
        {
            "address": "google_storage_bucket.eu_bucket",
            "type": "google_storage_bucket",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-eu-bucket",
                    "location": "europe-west4",
                    "encryption": [{"default_kms_key_name": "key"}]
                }
            }
        }
    ]
}

us_zone_plan := {
    "resource_changes": [
        {
            "address": "google_compute_instance.us_vm",
            "type": "google_compute_instance",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-us-vm",
                    "machine_type": "e2-medium",
                    "zone": "us-central1-a",
                    "labels": {},
                    "guest_accelerator": []
                }
            }
        }
    ]
}

us_region_plan := {
    "resource_changes": [
        {
            "address": "google_sql_database_instance.us_db",
            "type": "google_sql_database_instance",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-us-db",
                    "region": "us-central1"
                }
            }
        }
    ]
}

us_location_plan := {
    "resource_changes": [
        {
            "address": "google_storage_bucket.us_bucket",
            "type": "google_storage_bucket",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-us-bucket",
                    "location": "us-central1",
                    "encryption": [{"default_kms_key_name": "key"}]
                }
            }
        }
    ]
}

eu_multi_region_plan := {
    "resource_changes": [
        {
            "address": "google_storage_bucket.eu_bucket",
            "type": "google_storage_bucket",
            "change": {
                "actions": ["create"],
                "after": {
                    "name": "acme-eu-multi-bucket",
                    "location": "EU",
                    "encryption": [{"default_kms_key_name": "key"}]
                }
            }
        }
    ]
}
