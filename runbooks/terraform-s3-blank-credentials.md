# Terraform S3 backend fails deep in the run because credentials are blank

Tags: terraform, s3, garage, credentials, ansible-vault, workspace

## Symptoms
- `terraform init` appears to succeed, then `terraform workspace select` or `apply` fails.
- `Error: Failed to get existing workspaces: Unable to list objects in S3 bucket`.
- `api error InvalidAccessKeyId: The AWS Access Key Id you provided does not exist in our records` or `StatusCode: 403`.
- `echo "[$AWS_ACCESS_KEY_ID]"` in the shell that ran the playbook prints `[]`.

## Root cause
The playbook read the S3 backend credentials from `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` environment variables. A new shell, or forgetting to export them, passes blank values. A blank credential does not fail loudly at init; Terraform only errors when it first talks to the bucket.

## Fix
Store the backend credentials in Ansible Vault (`vault_aws_access_key_id`, `vault_aws_secret_access_key`) and pass them to the terraform module explicitly, then run with `--ask-vault-pass`. Add an `assert` task at the top of the play that fails fast if either value is empty.

## Needs approval
None for the fix. Do not paste the real keys into logs or chat.
