from fastapi import APIRouter

router = APIRouter()

STATUS_OK = 'ok'


@router.get('/health')
def get_health() -> dict[str, str]:

    '''
    Create health response payload for service checks.

    Returns:
    dict[str, str]: Service status payload.
    '''

    return {'status': STATUS_OK}


__all__ = ['router', 'get_health']
