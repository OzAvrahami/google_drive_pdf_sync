from dataclasses import dataclass
from typing import Optional


@dataclass
class InvoiceRecord:
    """
    Structured result produced by the invoice parser for one PDF file.

    All extraction fields (business_name, invoice_date, invoice_number,
    amount) are Optional.  None means the field could not be reliably
    located — not that it is zero or blank.  Callers should treat None
    as "unknown" rather than as a failure.

    The status field explains what happened to the document:
        processed               — accepted type, extraction was attempted
        skipped_receipt         — document is a standalone receipt (קבלה)
        skipped_invoice_receipt — document is חשבונית מס קבלה (combined)
        unrecognized_document_type — type not in accepted set
        parse_failed            — unexpected exception during parsing
    """

    file_name:      str           = ""
    folder_path:    str           = ""
    document_type:  Optional[str] = None
    status:         str           = "unrecognized_document_type"
    business_name:  Optional[str] = None
    invoice_date:   Optional[str] = None
    invoice_number: Optional[str] = None
    amount:         Optional[str] = None

    def to_dict(self) -> dict:
        """
        Return a plain dict suitable for constructing an Excel row.
        None values are replaced with empty strings so callers never
        need to guard against None in display/export logic.
        """
        return {
            "file_name":      self.file_name,
            "folder_path":    self.folder_path,
            "document_type":  self.document_type  or "",
            "status":         self.status,
            "business_name":  self.business_name  or "",
            "invoice_date":   self.invoice_date   or "",
            "invoice_number": self.invoice_number or "",
            "amount":         self.amount         or "",
        }
