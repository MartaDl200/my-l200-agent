# Required Google Cloud Service APIs
resource "google_project_service" "required_apis" {
  for_each = toset([
    "run.googleapis.com",
    "firestore.googleapis.com",
    "secretmanager.googleapis.com",
    "aiplatform.googleapis.com",
    "dlp.googleapis.com",
    "cloudtrace.googleapis.com",
    "cloudlogging.googleapis.com"
  ])
  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

# ---------------------------------------------------------------------
# 1. Secret Manager: Store GEMINI_API_KEY securely
# ---------------------------------------------------------------------
resource "google_secret_manager_secret" "gemini_api_key" {
  secret_id = var.gemini_api_key_secret_name
  project   = var.project_id

  replication {
    auto {}
  }

  labels = {
    app         = var.app_name
    environment = var.environment
    managed_by  = "terraform"
  }

  depends_on = [google_project_service.required_apis]
}

# ---------------------------------------------------------------------
# 2. Firestore: Native Mode Database for Persistent Session State
# ---------------------------------------------------------------------
resource "google_firestore_database" "session_db" {
  project     = var.project_id
  name        = var.firestore_database_name
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  concurrency_mode                = "OPTIMISTIC"
  app_engine_integration_mode     = "DISABLED"
  delete_protection_state         = "DELETE_PROTECTION_ENABLED"
  deletion_policy                 = "ABANDON"

  depends_on = [google_project_service.required_apis]
}

# ---------------------------------------------------------------------
# 3. Dedicated Service Account with Least-Privilege IAM Roles
# ---------------------------------------------------------------------
resource "google_service_account" "agent_service_account" {
  project      = var.project_id
  account_id   = "${var.app_name}-sa"
  display_name = "Gemini Enterprise Onboarding Multi-Agent Service Account"
}

# Grant Secret Manager Access
resource "google_secret_manager_secret_iam_member" "secret_accessor" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.gemini_api_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_service_account.email}"
}

# Grant Firestore Access
resource "google_project_iam_member" "firestore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.agent_service_account.email}"
}

# Grant Vertex AI User Access (for Gemini 2.5 Pro / Flash models)
resource "google_project_iam_member" "vertex_ai_user" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.agent_service_account.email}"
}

# Grant Cloud DLP User Access (for PII de-identification)
resource "google_project_iam_member" "dlp_user" {
  project = var.project_id
  role    = "roles/dlp.user"
  member  = "serviceAccount:${google_service_account.agent_service_account.email}"
}

# Grant Cloud Trace Agent Access (for OpenTelemetry tracing)
resource "google_project_iam_member" "trace_agent" {
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.agent_service_account.email}"
}

# ---------------------------------------------------------------------
# 4. Cloud Run Service: Multi-Agent Deployment
# ---------------------------------------------------------------------
resource "google_cloud_run_v2_service" "agent_service" {
  name     = "${var.app_name}-svc"
  location = var.region
  project  = var.project_id

  template {
    service_account = google_service_account.agent_service_account.email

    scaling {
      min_instance_count = 1
      max_instance_count = 10
    }

    containers {
      image = var.container_image

      resources {
        limits = {
          cpu    = "2"
          memory = "4Gi"
        }
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_REGION"
        value = var.region
      }
      env {
        name  = "COORDINATOR_MODEL"
        value = "gemini-2.5-pro"
      }
      env {
        name  = "DISCOVERY_MODEL"
        value = "gemini-2.5-flash"
      }
      env {
        name  = "SPECIALIST_MODEL"
        value = "gemini-2.5-flash"
      }
      env {
        name  = "FIRESTORE_DATABASE"
        value = var.firestore_database_name
      }
      env {
        name  = "FIRESTORE_COLLECTION"
        value = "gemini_onboarding_sessions"
      }
      env {
        name  = "GEMINI_API_KEY_SECRET_NAME"
        value = google_secret_manager_secret.gemini_api_key.secret_id
      }
      env {
        name  = "ENABLE_MODEL_ARMOR"
        value = "true"
      }
      env {
        name  = "REQUIRE_HUMAN_CONFIRMATION"
        value = "true"
      }

      # Mount secret directly to environment securely
      env {
        name = "GEMINI_API_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.gemini_api_key.secret_id
            version = "latest"
          }
        }
      }

      ports {
        container_port = 8080
      }
    }
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  depends_on = [
    google_project_service.required_apis,
    google_secret_manager_secret_iam_member.secret_accessor
  ]
}
