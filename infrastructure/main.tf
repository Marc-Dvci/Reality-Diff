locals {
  services = toset([
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "firestore.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "storage.googleapis.com",
  ])
}

resource "google_artifact_registry_repository" "containers" {
  location      = var.region
  repository_id = var.artifact_repository
  description   = "Reality Diff immutable Cloud Run images"
  format        = "DOCKER"

  docker_config {
    immutable_tags = true
  }

  depends_on = [google_project_service.required]
}

resource "google_project_service" "required" {
  for_each           = local.services
  service            = each.value
  disable_on_destroy = false
}

resource "google_service_account" "runtime" {
  account_id   = "reality-diff-runtime"
  display_name = "Reality Diff runtime"
}

resource "google_storage_bucket" "media" {
  name                        = "${var.project_id}-reality-diff-media"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  lifecycle_rule {
    condition {
      age = 30
    }
    action {
      type = "AbortIncompleteMultipartUpload"
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_firestore_database" "world" {
  project                 = var.project_id
  name                    = "(default)"
  location_id             = var.region
  type                    = "FIRESTORE_NATIVE"
  delete_protection_state = "DELETE_PROTECTION_ENABLED"
  deletion_policy         = "ABANDON"
  depends_on              = [google_project_service.required]
}

resource "google_pubsub_topic" "ingestion" {
  name       = "reality-diff-ingestion"
  depends_on = [google_project_service.required]
}

resource "google_pubsub_topic" "dead_letter" {
  name       = "reality-diff-ingestion-dead-letter"
  depends_on = [google_project_service.required]
}

# Shared secret gating the asynchronous state-construction endpoint. The same value is
# handed to the Cloud Run container and embedded in the push subscription URL, so only
# Pub/Sub can drive the stage even though the demo service permits public invoke.
resource "random_password" "pipeline_token" {
  length  = 32
  special = false
}

resource "google_pubsub_subscription" "ingestion" {
  name                       = "reality-diff-ingestion-worker"
  topic                      = google_pubsub_topic.ingestion.id
  ack_deadline_seconds       = 120
  message_retention_duration = "86400s"

  # Push delivery to the scale-to-zero Cloud Run service: the state-construction stage runs
  # only when a media.indexed event arrives, so there is still no always-on worker. OIDC
  # authenticates the push at the Cloud Run layer; the token gates it at the app layer.
  push_config {
    push_endpoint = "${google_cloud_run_v2_service.app.uri}/api/v1/pipeline/media-indexed?token=${random_password.pipeline_token.result}"

    oidc_token {
      service_account_email = google_service_account.runtime.email
    }
  }

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "300s"
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.dead_letter.id
    max_delivery_attempts = 5
  }
}

# Pub/Sub mints the OIDC token as the runtime service account, and delivers it to Cloud Run.
resource "google_service_account_iam_member" "pubsub_token_creator" {
  service_account_id = google_service_account.runtime.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_cloud_run_v2_service_iam_member" "pipeline_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.runtime.email}"
}

data "google_project" "current" {
  project_id = var.project_id
}

check "project_identity" {
  assert {
    condition     = data.google_project.current.number == var.project_number
    error_message = "Project ID does not resolve to the expected Reality Diff project number."
  }
}

resource "google_pubsub_topic_iam_member" "dead_letter_publisher" {
  topic  = google_pubsub_topic.dead_letter.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_subscription_iam_member" "forwarder_subscriber" {
  subscription = google_pubsub_subscription.ingestion.name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_project_iam_member" "runtime_roles" {
  for_each = toset([
    "roles/aiplatform.user",
    "roles/datastore.user",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_storage_bucket_iam_member" "runtime_media" {
  bucket = google_storage_bucket.media.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_pubsub_topic_iam_member" "runtime_publisher" {
  topic  = google_pubsub_topic.ingestion.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_cloud_run_v2_service" "app" {
  name                = var.service_name
  location            = var.region
  deletion_protection = false

  template {
    service_account                  = google_service_account.runtime.email
    timeout                          = "300s"
    max_instance_request_concurrency = 8

    scaling {
      min_instance_count = 0
      max_instance_count = 2
    }

    containers {
      image = var.image
      ports {
        container_port = 8080
      }
      resources {
        limits = { cpu = "1", memory = "512Mi" }
      }
      env {
        name  = "REALITYDIFF_ENV"
        value = "production"
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = "global"
      }
      env {
        name  = "REALITYDIFF_MEDIA_BUCKET"
        value = google_storage_bucket.media.name
      }
      env {
        name  = "REALITYDIFF_PUBSUB_TOPIC"
        value = google_pubsub_topic.ingestion.name
      }
      env {
        name  = "REALITYDIFF_PIPELINE_TOKEN"
        value = random_password.pipeline_token.result
      }
      env {
        name  = "REALITYDIFF_GEMINI_MODEL"
        value = "gemini-3.7-flash"
      }
      env {
        name  = "REALITYDIFF_TRIAGE_MODEL"
        value = "gemini-3.5-flash-lite"
      }
      env {
        name  = "REALITYDIFF_EMBEDDING_MODEL"
        value = "gemini-embedding-2"
      }
      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = "true"
      }
      startup_probe {
        initial_delay_seconds = 1
        timeout_seconds       = 2
        period_seconds        = 3
        failure_threshold     = 10
        http_get {
          path = "/ready"
          port = 8080
        }
      }
      liveness_probe {
        timeout_seconds   = 2
        period_seconds    = 30
        failure_threshold = 3
        http_get {
          path = "/health"
          port = 8080
        }
      }
    }
  }

  depends_on = [
    google_project_service.required,
    google_project_iam_member.runtime_roles,
    google_storage_bucket_iam_member.runtime_media,
    google_pubsub_topic_iam_member.runtime_publisher,
    google_firestore_database.world,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "public" {
  count    = var.public_demo ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.app.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
