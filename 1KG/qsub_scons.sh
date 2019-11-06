#!usr/bin/bash

# cd /net/harris/vol1/project/mushi
# source activate mushi

# linux
# n_jobs=`nproc --all`
# mac
n_jobs=`sysctl -n hw.physicalcpu`

bcfs="../data/bcf_files"
ancs="../data/human_ancestor_GRCh37_e59"
sample_pops="../data/integrated_call_samples_v3.20130502.ALL.panel"
k="3"
mutation_rate="1.1e-8"
phastcons="../data/phastConsElements100way.txt.gz"
repeats="../data/nestedRepeats.txt.gz"

outdir="scons_output_EUR"

no_exec="--no-exec"

cmd="scons --bcfs=${bcfs} --ancs=${ancs} --mutation_rate=${mutation_rate} --kmer=${k} --phastcons=${phastcons} --repeats=${repeats} --jobs=${n_jobs} --outdir=${outdir} ${debug} ${no_exec} --sample_pops=${sample_pops} ${gl}"
echo $cmd
$cmd
