output "cloud_run_service_url" {
  description = "Public or internal invocation URL for the Cloud Run agent service."
  value       = google_cloud_run_v2_service.agent_service.uri
}

output "firestore_database_id" {
  description = "The ID of the provisioned Firestore Native database."
  value       = google_firestore_database.session_db.name
}

output "secret_manager_secret_id" {
  description = "The Resource ID for the Gemini API Key Secret in Secret Manager."
  value       = google_secret_manager_secret.gemini_api_key.id
}

output "agent_service_account_email" {
  description = "Email of the dedicated least-privilege IAM service account."
  value       = google_service_account.agent_service_account.email
}
