# AWS Permissions

`lfguard` uses AWS Lake Formation APIs through boto3 only when live AWS state or
execution is requested. Offline `audit` and `plan` commands do not need AWS
credentials.

Exact permissions vary by resource type and by your Lake Formation
administration model. Start with a read-only role for audit and plan workflows,
then use a separate apply role for execution.

## Read-Only Inventory Role

Use this for `lfguard snapshot`, or for `lfguard audit` and `lfguard plan` when
`--current-snapshot` is not provided and live AWS inventory is loaded.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lakeformation:GetLFTag",
        "lakeformation:GetResourceLFTags",
        "lakeformation:ListPermissions"
      ],
      "Resource": "*"
    }
  ]
}
```

Depending on your environment, you may also need Glue read permissions for
catalog discovery handled outside `lfguard`, such as:

```json
{
  "Effect": "Allow",
  "Action": [
    "glue:GetDatabase",
    "glue:GetDatabases",
    "glue:GetTable",
    "glue:GetTables"
  ],
  "Resource": "*"
}
```

## Apply Role

Use this only for reviewed apply workflows.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lakeformation:CreateLFTag",
        "lakeformation:UpdateLFTag",
        "lakeformation:AddLFTagsToResource",
        "lakeformation:RemoveLFTagsFromResource",
        "lakeformation:GrantPermissions",
        "lakeformation:RevokePermissions"
      ],
      "Resource": "*"
    }
  ]
}
```

For production use, scope the role with your existing AWS account boundaries,
Lake Formation administrator model, permission boundaries, and deployment
process. Keep revoke and tag removal permissions out of routine automation if
your governance process requires separate approval for destructive changes.
