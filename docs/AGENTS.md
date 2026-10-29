# Unattended export research

Meta centralizes Instagram Download Your Information in Accounts Center: https://about.fb.com/news/2023/10/manage-your-information-across-apps/

Meta's official Instagram API collection describes professional-account messaging and its limitations: https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api

A future agent tool can parse an account archive locally and expose range/date/CSV operations without an open Instagram tab. Automating live personal DMs instead requires a managed authenticated browser/session; this is an engineering inference, not an officially supported history API. No unattended implementation is included. A read-only live probe of the legacy direct_v2 endpoint in this session returned HTML instead of JSON, so it was not adopted.
