from __future__ import annotations

from typing import Any

from ..models import PaperAccess, ProviderError
from .base import ProviderClient, extract_doi


class UnpaywallProvider(ProviderClient):
    provider_id = "unpaywall"
    min_interval = 0.2
    base_url = "https://api.unpaywall.org/v2"

    async def find_access(self, identifier: str) -> PaperAccess:
        if not self.settings.contact_email:
            raise ProviderError(self.provider_id, "contact_email is required")
        doi = extract_doi(identifier)
        if not doi:
            raise ProviderError(self.provider_id, "identifier is not a DOI")
        data = await self.get_json(f"{self.base_url}/{doi}", params={"email": self.settings.contact_email})
        locations: list[dict[str, Any]] = []
        best = data.get("best_oa_location")
        if isinstance(best, dict):
            locations.append(best)
        extra = data.get("oa_locations")
        if isinstance(extra, list):
            locations.extend(item for item in extra if isinstance(item, dict))
        for loc in locations:
            pdf_url = str(loc.get("url_for_pdf") or "").strip()
            landing_url = str(loc.get("url") or loc.get("url_for_landing_page") or "").strip()
            if pdf_url or landing_url:
                return PaperAccess(
                    available=bool(pdf_url),
                    pdf_url=pdf_url,
                    landing_url=landing_url,
                    source=self.provider_id,
                    version=str(loc.get("version") or loc.get("host_type") or "open_access"),
                    paper_id=doi,
                    license=str(loc.get("license") or ""),
                )
        raise ProviderError(self.provider_id, "no open access location")
