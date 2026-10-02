"""The license acknowledgment record, `acknowledgment.json` (docs/contracts.md, license
acknowledgment). It has no schema version: it holds exactly these four fields.
"""

from typing import Literal

from trialfolio.contracts.common import ContractModel, LicenseId, NonEmptyText, UtcDatetime


class AcknowledgmentRecord(ContractModel):
    """A user's acknowledgment of one license identifier and one notice version. It holds no
    identity, account, financial, or family information, and it's never transmitted."""

    license_id: LicenseId
    notice_version: NonEmptyText
    acknowledged_at: UtcDatetime
    method: Literal["interactive", "command"]
