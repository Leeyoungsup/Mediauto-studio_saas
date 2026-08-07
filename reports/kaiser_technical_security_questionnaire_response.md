# Kaiser Permanente – Technical Security Questionnaire Response

This document contains responses to the technical and infrastructure-related questions only. Questions concerning certifications, personnel screening, legal matters, corporate identity, and contractual sub-vendor notification are outside the technical scope of this document.

The project currently implements application-level authentication, role-based access control, MFA, audit logging, media-request signing, and file-integrity verification. The selected production deployment must also have the infrastructure controls described below enabled and verified before submission.

Only one deployment option should be submitted to Kaiser Permanente after the hosting architecture is finalized.

---

## Option A — AWS U.S. Region Deployment

### 2. Encryption at rest and in transit

The de-identified image set and associated AI outputs are encrypted at rest within the dedicated AWS U.S. environment. WSI files, AI results, Virtual Stain results, tile caches, annotations, databases, and backups are stored on encrypted AWS storage volumes or buckets. AWS KMS is used for encryption-key management.

All user and service traffic is encrypted in transit using HTTPS/TLS 1.2 or later. Connections to the application database use authenticated TLS. The application also uses bcrypt password hashing, AES-256-GCM encryption for MFA secrets, and short-lived HMAC-signed media tickets for tile and image requests.

### 3. Access-control model

The platform uses least-privilege, role-based access control:

- `admin`: user, project, and system administration;
- `doctor`: AI analysis and annotation functions; and
- `viewer`: approved slide viewing without modification privileges.

Only specifically approved personnel assigned to the KP project may access KP data. Application permissions and AWS IAM permissions are separated, and end users do not receive direct access to the database, S3 buckets, or server file system. MFA is required for authenticated access.

### 5. Logging, monitoring, and incident response

The platform records authentication events, failed logins, slide access, AI-processing activity, administrative actions, and permission changes. Audit records include the relevant user, timestamp, source information, and change details. Audit records are linked using an HMAC chain so that tampering can be detected.

The AWS environment also monitors API access, storage access, database events, GPU/compute health, authentication anomalies, and infrastructure errors. The incident-response process includes access revocation, session termination, network isolation where necessary, preservation of relevant logs, investigation, remediation, and recovery.

### 6. Retention and destruction

The agreed retention period is six months from the date the de-identified image set is received.

At the end of the study or when the approved retention period expires, the following are deleted from the production environment and applicable backups:

- de-identified WSI files;
- AI and Virtual Stain outputs;
- tile caches;
- annotation and review data;
- related database records;
- temporary processing files; and
- applicable snapshots and backup copies.

Deletion is verified across active storage, databases, snapshots, and backup-retention systems. No indefinite retention is intended.

### 7. Hosting and data location

The de-identified image set is stored and processed in a dedicated AWS environment located in a U.S. AWS Region.

Application services, GPU processing, databases, storage, and backups are restricted to the approved U.S. AWS environment.

### 8. Cloud provider / sub-vendor

Amazon Web Services (AWS) is used as the cloud infrastructure service provider and sub-vendor. AWS provides the compute, GPU, networking, storage, backup, and monitoring infrastructure. No external annotation or AI-processing sub-vendor is used by the platform.

### 9. Access by South Korea personnel

South Korea personnel access the data remotely through the U.S.-hosted AWS environment using authenticated HTTPS and/or VPN connections. No routine production copy or backup of the KP image set is stored in South Korea. Operational data remains in the approved U.S. environment.

### 10. Standalone KP-dedicated environment

Yes. The KP project is operated in a dedicated environment consisting of dedicated application and GPU resources, a dedicated database, dedicated storage, and isolated network controls within the U.S. AWS environment.

### 11. Designated work location and enforcement

Personnel assigned to the KP account are required to use approved company locations and company-managed devices. Access is enforced through VPN and/or IP allowlisting, MFA, user-specific access logging, and administrative approval of project access. Access from unapproved locations or networks is blocked.

### 12. Approved-country controls

Service access is restricted to approved operating countries, South Korea and the United States. VPN policies, source-IP restrictions, AWS security groups, firewall rules, MFA, and access-log review are used to enforce and verify the location restrictions.

### 13. Vendor-owned devices

Work on the KP account is performed using vendor-owned or vendor-managed devices. Devices use full-disk encryption, centrally managed security settings, endpoint protection, security updates, and access controls appropriate for the project.

### 14. Personal-device model

No personal-device or hybrid personal-device workflow is permitted. KP data is accessed only through the approved environment and vendor-managed devices.

### 15. Download, local storage, replication, and backup controls

Direct end-user access to S3, databases, and server storage is disabled. Access is provided through the authenticated application. The environment applies least-privilege IAM policies, private storage access, download restrictions, managed-device controls, and DLP/endpoint policies where applicable.

Production data and backups are restricted to the approved U.S. AWS environment. Replication to South Korea, unapproved regions, personal devices, removable media, or unapproved storage is prohibited and technically restricted through network, IAM, storage, and endpoint controls.

### 16. Personnel list and provisioning/deprovisioning

The named personnel assigned to the KP account will be provided separately by the project owner through an approved secure channel. From a technical perspective, provisioning requires manager/project approval, identity verification, MFA enrollment, and assignment of the minimum required role.

When personnel leave the project, their application, VPN, AWS/IAM, and active-session access are revoked. Access changes are logged.

### 17. Offshore sub-vendors

No offshore annotation, AI-support, or storage sub-vendor is used. AWS is the U.S.-based cloud infrastructure sub-vendor described in Question 8.

---

## Option B — U.S.-Located Dedicated GPU Server Deployment

### 2. Encryption at rest and in transit

The de-identified image set and associated AI outputs are stored and processed on a dedicated GPU server physically located in the United States. The server operating system, WSI storage, AI-result storage, tile cache, annotation storage, database, and backup volumes use full-disk or volume-level encryption.

All user and service traffic is encrypted in transit using HTTPS/TLS 1.2 or later. Database connections use authentication and TLS. The application also uses bcrypt password hashing, AES-256-GCM encryption for MFA secrets, and short-lived HMAC-signed media tickets for tile and image requests.

### 3. Access-control model

The platform uses least-privilege, role-based access control:

- `admin`: user, project, and system administration;
- `doctor`: AI analysis and annotation functions; and
- `viewer`: approved slide viewing without modification privileges.

Only approved personnel assigned to the KP project may access KP data. End users do not receive direct operating-system, database, or file-system access. Server, VPN, and application permissions are separately managed, and MFA is required.

### 5. Logging, monitoring, and incident response

The platform records authentication events, failed logins, slide access, AI-processing activity, administrative actions, and permission changes. Audit records include the relevant user, timestamp, source information, and change details. An HMAC chain is used to detect audit-log tampering.

The server environment also monitors VPN access, operating-system logins, file access, GPU/CPU utilization, disk capacity, backup activity, authentication anomalies, and service errors. The incident-response process includes account and session revocation, network isolation where necessary, log preservation, investigation, remediation, and recovery.

### 6. Retention and destruction

The agreed retention period is six months from the date the de-identified image set is received.

At the end of the study or when the approved retention period expires, the following are deleted from the U.S. server and applicable backups:

- de-identified WSI files;
- AI and Virtual Stain outputs;
- tile caches;
- annotation and review data;
- related database records;
- temporary processing files; and
- backup copies.

Deletion is verified across the active server, database, backup media, and any hosted storage used for disaster recovery. No indefinite retention is intended.

### 7. Hosting and data location

The de-identified image set is stored and processed on a dedicated GPU server physically located within the United States. The application, GPU processing, database, storage, and backups remain within the approved U.S. environment.

### 8. Cloud provider / sub-vendor

No commercial cloud provider is used for the production image-processing environment. The platform is operated on the U.S.-located dedicated GPU server. If the server is hosted by a third-party U.S. data-center operator, that operator will be listed separately as the hosting service provider.

### 9. Access by South Korea personnel

South Korea personnel access the data remotely through authenticated HTTPS and/or VPN connections to the U.S.-located server. No routine production copy or backup of the KP image set is stored in South Korea. Operational data remains on the approved U.S. server and its approved U.S. backup media.

### 10. Standalone KP-dedicated environment

Yes. The KP project is operated on a dedicated U.S.-located GPU server with dedicated storage, database, and network controls. The environment is isolated from unrelated projects.

### 11. Designated work location and enforcement

Personnel assigned to the KP account are required to use approved company locations and company-managed devices. Access is enforced through VPN and/or IP allowlisting, MFA, user-specific access logging, and administrative approval. Access from unapproved locations or networks is blocked.

### 12. Approved-country controls

Service access is restricted to approved operating countries, South Korea and the United States. VPN policy, firewall rules, source-IP restrictions, MFA, and access-log review are used to enforce and verify the country restrictions.

### 13. Vendor-owned devices

Work on the KP account is performed using vendor-owned or vendor-managed devices. Devices use full-disk encryption, centrally managed security settings, endpoint protection, security updates, and project-specific access controls.

### 14. Personal-device model

No personal-device or hybrid personal-device workflow is permitted. KP data is accessed only through the approved environment and vendor-managed devices.

### 15. Download, local storage, replication, and backup controls

Direct end-user access to the server file system and database is disabled. Access is provided through the authenticated application. Server firewall rules, VPN controls, operating-system permissions, managed-device controls, download restrictions, and DLP/endpoint policies are used to restrict data export.

Production data and backups are restricted to the approved U.S. server environment. Replication to South Korea, personal devices, removable media, or unapproved storage is prohibited and technically restricted through network, operating-system, application, and endpoint controls.

### 16. Personnel list and provisioning/deprovisioning

The named personnel assigned to the KP account will be provided separately by the project owner through an approved secure channel. From a technical perspective, provisioning requires manager/project approval, identity verification, MFA enrollment, and minimum-role assignment. When personnel leave the project, their application, VPN, server, and active-session access are revoked. Access changes are logged.

### 17. Offshore sub-vendors

No offshore annotation, AI-support, or storage sub-vendor is used. The production environment is operated on the dedicated GPU server located in the United States. Any third-party U.S. data-center or server-hosting operator will be identified separately if applicable.

---

## Items outside the technical scope of this document

Questions 1, 4, 18, 19, and 20 require confirmation from the corporate, legal, HR, or contracting owner. The named personnel list in Question 16 will be provided separately and is not included in this technical document.
