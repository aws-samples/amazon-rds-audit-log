class InvalidInputError(Exception):
    pass


class InvalidDataOrConfigurationError(Exception):
    pass


class FailedAuditLogEnableError(Exception):
    pass


class FailedAuditExportToS3(Exception):
    pass

