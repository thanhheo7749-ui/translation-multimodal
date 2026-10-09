from abc import ABC, abstractmethod
from backend.translation.contracts import TranslationRequest, TranslationResponse

class BaseTranslator(ABC):
    """
    Abstract base class for all translation engines (Local LLM, Cloud LLM, Mock).
    """
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name of the translation provider."""
        pass

    @abstractmethod
    async def translate(self, request: TranslationRequest) -> TranslationResponse:
        """
        Translates the given speech text using available visual and discursive context.
        """
        pass
