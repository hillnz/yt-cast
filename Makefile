TF_FLAGS := -var-file=deploy.tfvars

TFVAR = $(shell awk -F\" '/^[[:space:]]*$(1)[[:space:]]*=/{print $$2; exit}' deploy.tfvars)

.PHONY: plan apply deploy-dlp

plan:
	terraform plan $(TF_FLAGS)

apply:
	terraform apply $(TF_FLAGS)

deploy-dlp:
	gcloud run deploy $(call TFVAR,dlp_service_name) \
		--image $(call TFVAR,dlp_image) \
		--region $(call TFVAR,gcp_region) \
		--project $(call TFVAR,gcp_project_id)
