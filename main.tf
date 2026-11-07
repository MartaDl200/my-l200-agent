terraform {
  required_version = ">= 1.5.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.20.0"
    }
    google-beta = {
      source  = "hashicorp/google-beta"
      version = "~> 5.20.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "google-beta" {
  project = var.project_id
  region  = var.region
}

# Delegate to terraform/ module for complete resource management
module "gemini_agent_infrastructure" {
  source                     = "./terraform"
  project_id                 = var.project_id
  region                     = var.region
  environment                = var.environment
  app_name                   = var.app_name
  container_image            = var.container_image
  firestore_database_name    = var.firestore_database_name
  gemini_api_key_secret_name = var.gemini_api_key_secret_name
}

output "cloud_run_service_url" {
  description = "The deployed Cloud Run service URL."
  value       = module.gemini_agent_infrastructure.cloud_run_service_url
}

output "firestore_database_id" {
  description = "The provisioned Firestore database ID."
  value       = module.gemini_agent_infrastructure.firestore_database_id
}

output "secret_manager_secret_id" {
  description = "The Secret Manager secret ID for Gemini API key."
  value       = module.gemini_agent_infrastructure.secret_manager_secret_id
}
