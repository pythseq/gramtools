import logging
import itertools
import collections
from Bio import SeqIO

from . import prg

log = logging.getLogger('gramtools')


def parse_args(common_parser, subparsers):
    parser = subparsers.add_parser('kmers',
                                   parents=[common_parser])

    parser.add_argument('--kmer-size', help='',
                        type=int,
                        required=True)
    parser.add_argument('--reference', help='',
                        type=str,
                        required=True)
    parser.add_argument('--kmer-region-size',
                        dest='kmer_region_size',
                        help='',
                        type=int,
                        required=True)
    parser.add_argument('--output-fpath', help='',
                        type=str,
                        required=True)

    parser.add_argument('--nonvariant-kmers', help='',
                        action='store_true')


def _filter_regions(regions, nonvariant_kmers):
    """Yield regions with filtering based on a region's variant site status."""
    if nonvariant_kmers:
        for region in regions:
            yield region
        return

    for region in regions:
        if region.is_variant_site:
            yield region


def _truncate_tail_alleles(max_overshoot_bases, inrange_alleles, reverse):
    if not inrange_alleles:
        return inrange_alleles

    if reverse:
        truncated_alleles = [allele[-max_overshoot_bases:]
                             for allele in inrange_alleles[0]]
        inrange_alleles[0] = truncated_alleles

    else:
        truncated_alleles = [allele[:max_overshoot_bases]
                             for allele in inrange_alleles[-1]]
        inrange_alleles[-1] = truncated_alleles
    return inrange_alleles


def _directional_alleles_range(kmer_region_size, start_region,
                               regions, reverse):
    """Return list of regions which are within a given base distance
    of a starting regions.

    The starting region is not included in the returned region range.
    """
    min_distance = 0
    max_distance = 0
    last_max_allele_len = 0

    passed_kmer_region = False

    inrange_alleles = collections.deque()
    for region in regions.range(start_region, reverse=reverse):
        if reverse:
            inrange_alleles.appendleft(region.alleles)
        else:
            inrange_alleles.append(region.alleles)

        passed_kmer_region = (min_distance + region.min_allele_len
                              >= kmer_region_size)
        if passed_kmer_region:
            break

        min_distance += region.min_allele_len
        max_distance += region.max_allele_len
        last_max_allele_len = region.max_allele_len

    if not passed_kmer_region:
        max_overshoot_bases = (kmer_region_size
                               - max_distance
                               - last_max_allele_len)
    else:
        max_overshoot_bases = kmer_region_size - max_distance

    if max_overshoot_bases <= 0:
        return inrange_alleles

    inrange_alleles = _truncate_tail_alleles(max_overshoot_bases,
                                             inrange_alleles, reverse)
    return inrange_alleles


def _alleles_within_range(kmer_region_size, start_region, regions):
    """Return regions within a max base distance of start region.
    Start region is not included in the distance measure.
    """
    reverse_alleles = _directional_alleles_range(kmer_region_size,
                                                 start_region, regions,
                                                 reverse=True)
    star_region_alleles = collections.deque([start_region.alleles])
    forward_alleles = _directional_alleles_range(kmer_region_size,
                                                 start_region, regions,
                                                 reverse=False)
    return reverse_alleles + star_region_alleles + forward_alleles


def _genome_paths(ordered_alleles):
    """Generate all genome paths which exist for a given region range."""
    for genome_path in itertools.product(*ordered_alleles):
        yield ''.join(genome_path)


def _kmers_from_genome_paths(genome_paths, kmer_size):
    """Generate all kmers which exist for a list of genome paths."""
    seen_kmers = set()
    for path in genome_paths:
        for i in range(len(path)):
            if i + kmer_size > len(path):
                break
            kmer = path[i: i + kmer_size]

            if kmer not in seen_kmers:
                seen_kmers.add(kmer)
                yield kmer


def _generate(kmer_region_size, kmer_size, regions, nonvariant_kmers):
    """Generate kmers."""
    seen_kmers = set()
    for start_region in _filter_regions(regions, nonvariant_kmers):
        ordered_alleles = _alleles_within_range(kmer_region_size,
                                                start_region,
                                                regions)
        genome_paths = _genome_paths(ordered_alleles)
        kmers = _kmers_from_genome_paths(genome_paths, kmer_size)
        for kmer in kmers:
            if kmer not in seen_kmers:
                yield kmer
                seen_kmers.add(kmer)


def _dump_kmers(kmers, output_fpath):
    count_written = 0
    with open(output_fpath, 'w') as fhandle:
        for kmer in kmers:
            fhandle.write(kmer + '\n')
            count_written += 1
    return count_written


def _dump_masks(sites, alleles, args):
    log.debug('Writing sites mask to file')
    with open(args.sites_mask_fpath, 'w') as fhandle:
        fhandle.write(sites)
    log.debug('Writing alleles mask to file')
    with open(args.allele_mask_fpath, 'w') as fhandle:
        fhandle.write(alleles)


def run(args):
    log.info('Start process: generate kmers')

    log.debug('Parsing PRG')
    fasta_seq = str(SeqIO.read(args.reference, 'fasta').seq)
    regions = prg.parse(fasta_seq)

    log.debug('Generating Kmers')
    kmers = _generate(args.kmer_region_size,
                      args.kmer_size, regions,
                      args.nonvariant_kmers)

    log.debug('Writing kmers to file')
    count_written = _dump_kmers(kmers, args.output_fpath)
    log.debug('Number of kmers writen to file: %s', count_written)

    log.info('End process: generate kmers')
