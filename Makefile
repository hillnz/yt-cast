TF_FLAGS := -var-file=deploy.tfvars

.PHONY: plan apply

plan:
	terraform plan $(TF_FLAGS)

apply:
	terraform apply $(TF_FLAGS)
