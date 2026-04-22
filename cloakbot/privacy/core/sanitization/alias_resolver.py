from __future__ import annotations

from cloakbot.privacy.core.state.vault import _SessionMap


class AliasResolverAgent:
    """Resolve likely cross-turn aliases onto an existing placeholder."""

    def resolve(
        self,
        text: str,
        tag: str,
        smap: _SessionMap,
    ) -> str | None:
        existing = smap.lookup_placeholder(text)
        if existing is not None:
            return existing

        normalized = smap.normalize_text(text)
        if not normalized:
            return None

        candidates: list[str] = []
        for placeholder, entity in smap.placeholder_to_entity.items():
            if not placeholder.startswith(f"<<{tag}_"):
                continue
            if normalized in entity.normalized_aliases:
                candidates.append(placeholder)
                continue

            if tag == "PERSON":
                tokens = normalized.split()
                if len(tokens) == 1:
                    for alias in entity.normalized_aliases:
                        alias_tokens = alias.split()
                        if tokens[0] in alias_tokens:
                            candidates.append(placeholder)
                            break
                elif entity.normalized_aliases:
                    if any(
                        normalized.endswith(alias) or alias.endswith(normalized)
                        for alias in entity.normalized_aliases
                    ):
                        candidates.append(placeholder)

        if len(candidates) == 1:
            return candidates[0]
        return None


_RESOLVER = AliasResolverAgent()


def resolve_existing_placeholder(text: str, tag: str, smap: _SessionMap) -> str | None:
    return _RESOLVER.resolve(text, tag, smap)
