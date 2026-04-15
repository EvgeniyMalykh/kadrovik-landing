from django.http import JsonResponse


def healthcheck(request):
    return JsonResponse({'app': __name__, 'status': 'ok'})
