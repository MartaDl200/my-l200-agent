variable "project_id" {
  description = "The Google Cloud Project ID hosting the Gemini Enterprise Onboarding Agent."
  type        = string
  default     = "gemini-enterprise-onboarding"
}

variable "region" {
  description = "Primary Google Cloud Region for compute, storage, and Vertex AI endpoints."
  type        = string
  default     = "us-central1"
}

variable "environment" {
  description = "Deployment environment (dev, staging, prod)."
  type        = string
  default     = "prod"
}

variable "app_name" {
  description = "Application name used for naming cloud resources."
  type        = string
  default     = "gemini-enterprise-agent"
}

variable "container_image" {
  description = "Container image URL for the Google Cloud Run service."
  type        = string
  default     = "gcr.io/gemini-enterprise-onboarding/agent:latest"
}

variable "firestore_database_name" {
  description = "The Firestore database name for persistent session state."
  type        = string
  default     = "(default)"
}

variable "gemini_api_key_secret_name" {
  description = "Name of the Secret Manager secret storing the Gemini API key."
  type        = string
  default     = "gemini-api-key"
}
