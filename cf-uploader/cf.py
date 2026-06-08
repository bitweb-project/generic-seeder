""" Cloudflare interface — compatible with cloudflare library v3.x / v4.x / v5.x (new API)
    Original code was written for v2.x which used a completely different import and method names.
    
    Breaking changes from v2 → v3+:
      import CloudFlare                         → import cloudflare
      CloudFlare.CloudFlare(token=key)          → cloudflare.Cloudflare(api_token=key)
      cf.zones.get(params={name:..})            → cf.zones.list(name=..)
      cf.zones.dns_records.get(zone_id,..)      → cf.dns.records.list(zone_id=zone_id,..)
      cf.zones.dns_records.post(zone_id,data=.) → cf.dns.records.create(zone_id=zone_id,..)
      cf.zones.dns_records.delete(zone_id, id)  → cf.dns.records.delete(id, zone_id=zone_id)
      record['content'], record['id']           → record.content,  record.id
      _base.raw = True pagination hack          → auto-paginated iterators
"""
import logging
import cloudflare
import errors

logger = logging.getLogger(__name__)


def isipv6(ip):
    """ Extremely naive IPV6 check. """
    return ip.count(':') > 1


def _lookup_zone_id(cf_client, domain):
    """ Return the zone_id for a given domain using the cloudflare interface. """
    logger.info("Resolving cloudflare zoneid for domain name: {}".format(domain))
    zones = list(cf_client.zones.list(name=domain))

    if not len(zones):
        raise errors.ZoneNotFound("Could not find zone named: {}".format(domain))

    if len(zones) > 1:
        raise errors.TooManyZones("More than one zone found named: {}".format(domain))

    return zones[0].id


class CloudflareSeeder(object):
    """ Cloudflare abstraction layer allowing to manage DNS entries. """

    @staticmethod
    def from_configuration(configuration):
        """ Instantiate and return an instance from a configuration dict. """
        logger.debug("Creating CloudflareSeeder interface from configuration.")
        key    = configuration['cf_api_key'].replace('"', '')
        domain = configuration['cf_domain'].replace('"', '')
        name   = configuration['cf_domain_prefix'].replace('"', '')
        return CloudflareSeeder(key, domain, name)

    def __init__(self, key, domain, name):
        """ Constructor: set the member variables. """
        logger.debug("CloudflareSeeder creation for domain: {} name: {}".format(domain, name))
        self.cf = cloudflare.Cloudflare(api_token=key)
        self.domain = domain
        self.name   = name
        self._zone_id = None

    @property
    def zone_id(self):
        """ Resolve the zone id from the name if we haven't before. """
        if self._zone_id is None:
            self._zone_id = _lookup_zone_id(self.cf, self.domain)
        return self._zone_id

    def _full_name(self, flags=False):
        """ Build the full DNS record name. """
        parts = [self.name, self.domain]
        if flags:
            parts.insert(0, 'x9')
        return '.'.join(parts)

    def get_seed_records(self, flags=False):
        """
        Get seed DNS records (type A or AAAA) that match the record name.
        v5 API: dns.records.list() returns an auto-paginated iterable — no raw hack needed.
        The 'type' param only accepts a single value, so we fetch A and AAAA separately.
        """
        full_name = self._full_name(flags)
        zone_id   = self.zone_id
        records   = []

        for rec_type in ('A', 'AAAA'):
            logger.info("Fetching {} records for {}".format(rec_type, full_name))
            for record in self.cf.dns.records.list(zone_id=zone_id, name=full_name, type=rec_type):
                records.append(record)

        return records

    def get_seeds(self):
        """ Read the seeds for the zone and name in cloudflare. """
        logger.debug("Getting seeds from cloudflare")
        return [record.content for record in self.get_seed_records()]

    def _set_seed(self, seed, ttl=None, flags=False):
        """ Set either a flags or non-flags seed entry in cloudflare. """
        logger.debug("Setting seed {} in cloudflare".format(seed))
        rec_type    = 'AAAA' if isipv6(seed) else 'A'
        record_name = ('x9.' + self.name) if flags else self.name
        effective_ttl = ttl if ttl is not None else 1  # 1 = automatic in Cloudflare

        logger.debug("Posting record name={} type={} content={}".format(record_name, rec_type, seed))
        try:
            self.cf.dns.records.create(
                zone_id = self.zone_id,
                name    = record_name,
                type    = rec_type,
                content = seed,
                ttl     = effective_ttl,
                proxied = False,
            )
        except cloudflare.APIError as e:
            logger.error("Error setting seed through the cloudflare API: {}".format(e))

    def set_seed(self, seed, ttl=None):
        """ Add a new seed record to cloudflare with corresponding flagged entry. """
        self._set_seed(seed, ttl=ttl)
        self._set_seed(seed, ttl=ttl, flags=True)

    def delete_seeds(self, seeds):
        """ Delete the seeds' DNS entries in cloudflare. """
        logger.debug("Deleting seeds from cloudflare.")
        for seed_record in self.get_seed_records() + self.get_seed_records(flags=True):
            if seed_record.content in seeds:
                logger.debug("Deleting seed: {}".format(seed_record.content))
                self.cf.dns.records.delete(seed_record.id, zone_id=self.zone_id)

    def set_seeds(self, seeds, ttl=None):
        """ Set a list of seeds as DNS entries in cloudflare. """
        for seed in seeds:
            self.set_seed(seed, ttl)
