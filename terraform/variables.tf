variable "project_id" {
  description = "Google Cloud Project ID."
  type        = string
}

variable "region" {
  description = "Google Cloud Region."
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Target deployment tier."
  type        = string
  default     = "prod"
}

variable "app_name" {
  description = "Prefix identifier for provisioned resources."
  type        = string
  default     = "gemini-enterprise-agent"
}

variable "container_image" {
  description = "Docker image repository path for Cloud Run."
  type        = string
  default     = "gcr.io/gemini-enterprise-onboarding/agent:latest"
}

variable "firestore_database_name" {
  description = "Firestore database ID."
  type        = string
  default     = "(default)"
}

variable "gemini_api_key_secret_name" {
  description = "Secret Manager secret ID for GEMINI_API_KEY."
  type        = string
  default     = "gemini-api-key"
}
