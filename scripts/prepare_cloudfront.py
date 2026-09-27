"""Write a private CloudFront create-distribution-with-tags request; creates no AWS resources."""
import argparse
import json
import os
from pathlib import Path
import re
import uuid

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--origin-domain', required=True, help='EC2 public DNS hostname in Seoul')
parser.add_argument('--env-file', type=Path, default=Path('.env.aws.local'))
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
assert re.fullmatch(r'ec2-[0-9-]+\.ap-northeast-2\.compute\.amazonaws\.com', args.origin_domain), 'Use the actual Seoul EC2 public DNS hostname'
values = dict(line.split('=', 1) for line in args.env_file.read_text().splitlines() if '=' in line and not line.startswith('#'))
secret = values.get('ORIGIN_VERIFY_SECRET', '')
assert re.fullmatch(r'[a-f0-9]{64}', secret), 'Set a random 64-character hex origin secret'
config = {
    'CallerReference': 'bio3-' + uuid.uuid4().hex,
    'Comment': 'Bio-3 - same-origin service, no private response caching',
    'Origins': {'Quantity': 1, 'Items': [{
        'Id': 'bio3-web', 'DomainName': args.origin_domain,
        'CustomHeaders': {'Quantity': 1, 'Items': [{'HeaderName': 'X-Bio3-Origin', 'HeaderValue': secret}]},
        'CustomOriginConfig': {'HTTPPort': 80, 'HTTPSPort': 443, 'OriginProtocolPolicy': 'http-only',
            'OriginSslProtocols': {'Quantity': 1, 'Items': ['TLSv1.2']}, 'OriginReadTimeout': 30, 'OriginKeepaliveTimeout': 5},
    }]},
    'DefaultCacheBehavior': {
        'TargetOriginId': 'bio3-web', 'ViewerProtocolPolicy': 'redirect-to-https', 'Compress': True,
        'AllowedMethods': {'Quantity': 7, 'Items': ['GET', 'HEAD', 'OPTIONS', 'PUT', 'PATCH', 'POST', 'DELETE'],
            'CachedMethods': {'Quantity': 2, 'Items': ['GET', 'HEAD']}},
        'CachePolicyId': '4135ea2d-6df8-44a3-9df3-4b5a84be39ad',  # Managed-CachingDisabled
        'OriginRequestPolicyId': 'b689b0a8-53d0-40ab-baf2-68738e2966ac',  # Managed-AllViewerExceptHostHeader
    },
    'CustomErrorResponses': {'Quantity': 7, 'Items': [
        {'ErrorCode': code, 'ErrorCachingMinTTL': 0} for code in [400, 403, 404, 500, 502, 503, 504]
    ]},
    'ViewerCertificate': {'CloudFrontDefaultCertificate': True},
    'PriceClass': 'PriceClass_All', 'HttpVersion': 'http2', 'IsIPV6Enabled': True, 'Enabled': True,
}
request = {'DistributionConfig': config, 'Tags': {'Items': [{'Key': 'Project', 'Value': 'bio3'}]}}
with os.fdopen(os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as file:
    json.dump(request, file, indent=2)
print('Private CloudFront request saved. No distribution was created.')
