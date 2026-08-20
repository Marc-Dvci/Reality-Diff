output "service_url" {
  description = "Cloud Run service URL (authenticated unless public_demo is enabled)."
  value       = google_cloud_run_v2_service.app.uri
}

output "media_bucket" {
  value = google_storage_bucket.media.name
}

output "ingestion_topic" {
  value = google_pubsub_topic.ingestion.name
}

output "artifact_registry" {
  description = "Docker repository prefix for immutable Reality Diff images."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.containers.repository_id}"
}
