variable "project_id" {
  description = "Google Cloud project id."
  type        = string
  default     = "reality-diff"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    error_message = "project_id must be a valid Google Cloud project id."
  }
}

variable "project_number" {
  description = "Expected Google Cloud project number; prevents deploying into a similarly named project."
  type        = string
  default     = "284853036406"
  validation {
    condition     = can(regex("^[0-9]{6,20}$", var.project_number))
    error_message = "project_number must contain only digits."
  }
}

variable "region" {
  description = "Cloud Run and storage region."
  type        = string
  default     = "us-central1"
}

variable "image" {
  description = "Immutable Reality Diff container image reference."
  type        = string
}

variable "artifact_repository" {
  description = "Artifact Registry Docker repository id."
  type        = string
  default     = "reality-diff"
}

variable "service_name" {
  description = "Cloud Run service name."
  type        = string
  default     = "reality-diff"
}

variable "public_demo" {
  description = "Allow unauthenticated access. Keep false for private single-user deployments."
  type        = bool
  default     = false
}
