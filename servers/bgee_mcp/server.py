"""Bgee healthy wild-type gene expression via the public SPARQL endpoint."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from common.api import json_response, page
from common.http import identifier, text

mcp = FastMCP("bgee")
ENDPOINT = "https://www.bgee.org/sparql"

PREFIXES = """\
PREFIX efo: <http://www.ebi.ac.uk/efo/>
PREFIX dcterms: <http://purl.org/dc/terms/>
PREFIX genex: <http://purl.org/genex#>
PREFIX lscr: <http://purl.org/lscr#>
PREFIX obo: <http://purl.obolibrary.org/obo/>
PREFIX orth: <http://purl.org/net/orth#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX up: <http://purl.uniprot.org/core/>
"""

# Bgee labels genes, anatomical entities and species with free-text names;
# restrict literals to characters that cannot escape the SPARQL string context.
_NAME = r"[A-Za-z0-9_. '-]+"


def _name(value: str, name: str = "name") -> str:
    return identifier(value, _NAME, name).lower()


def _species_clause(species: str | None) -> str:
    if species is None:
        return ""
    literal = _name(species, "species")
    return (f"OPTIONAL {{ ?taxon up:scientificName|up:commonName ?spName . }} "
            f"FILTER (LCASE(?spName) = \"{literal}\") . ")


async def _query(select: str, where: str, limit: int, offset: int) -> dict:
    query = f"{PREFIXES}SELECT DISTINCT {select} WHERE {{ {where} }} LIMIT {limit} OFFSET {offset}"
    data, source = await json_response(
        ENDPOINT, {"query": query, "format": "application/sparql-results+json"})
    rows = [{variable: bound["value"] for variable, bound in binding.items()}
            for binding in data.get("results", {}).get("bindings", [])]
    return {**source, "sparql": query, "results": rows, **page(limit, offset)}


@mcp.tool()
async def bgee_species(limit: int = 20, offset: int = 0) -> dict:
    """List species present in Bgee with their scientific and common names."""
    where = ("?species a up:Taxon ; up:scientificName ?scientificName ; "
             "up:rank up:Species . OPTIONAL { ?species up:commonName ?commonName . }")
    return await _query("?species ?scientificName ?commonName", where, limit, offset)


@mcp.tool()
async def bgee_gene_info(ensembl_id: str) -> dict:
    """Retrieve Bgee gene metadata by Ensembl gene ID, including cross-references."""
    ensembl = identifier(ensembl_id.upper(), r"ENS[A-Z]+[0-9]{11}", "Ensembl gene ID")
    where = ("?seq a orth:Gene ; rdfs:label ?symbol ; dcterms:description ?description ; "
             "dcterms:identifier ?id ; orth:organism ?organism . "
             "OPTIONAL { ?seq lscr:xrefUniprot ?uniprot . } "
             "OPTIONAL { ?seq lscr:xrefEnsemblGene ?ensembl . } "
             "OPTIONAL { ?seq lscr:xrefNCBIGene ?ncbi . } "
             f"FILTER (?id = \"{ensembl}\")")
    return await _query("?symbol ?description ?id ?organism ?uniprot ?ensembl ?ncbi", where, 100, 0)


@mcp.tool()
async def bgee_gene_species(gene: str, limit: int = 20, offset: int = 0) -> dict:
    """List species in which a gene with the given name or symbol is present."""
    literal = _name(gene, "gene")
    where = ("?gene a orth:Gene ; rdfs:label ?geneName ; orth:organism ?organism . "
             "?organism obo:RO_0002162 ?taxon . ?taxon a up:Taxon ; "
             "up:scientificName ?scientificName . "
             f"FILTER (LCASE(?geneName) = \"{literal}\")")
    return await _query("?geneName ?scientificName", where, limit, offset)


@mcp.tool()
async def bgee_gene_expression(gene: str, species: str | None = None,
                               limit: int = 20, offset: int = 0) -> dict:
    """List anatomical entities where a gene is expressed in Bgee conditions."""
    literal = _name(gene, "gene")
    where = ("?seq a orth:Gene ; rdfs:label ?geneName ; genex:isExpressedIn ?anat . "
             "?anat a genex:AnatomicalEntity ; rdfs:label ?anatName . "
             f"FILTER (LCASE(?geneName) = \"{literal}\") {_species_clause(species)}")
    return await _query("?geneName ?anat ?anatName", where, limit, offset)


@mcp.tool()
async def bgee_gene_expression_scores(gene: str, species: str | None = None,
                                      limit: int = 20, offset: int = 0) -> dict:
    """List expressed anatomical entities with developmental stage and expression score.

    Scores come from Bgee expression calls; compare them only within one species
    and condition, not across genes or species.
    """
    literal = _name(gene, "gene")
    where = ("?seq a orth:Gene ; rdfs:label ?geneName ; orth:organism ?organism . "
             "?expression a genex:Expression ; genex:hasExpressionCondition ?condition ; "
             "genex:hasExpressionLevel ?score ; genex:hasSequenceUnit ?seq . "
             "?condition a genex:ExpressionCondition ; genex:hasAnatomicalEntity ?anat ; "
             "genex:hasDevelopmentalStage ?stage . "
             "?anat a genex:AnatomicalEntity ; rdfs:label ?anatName . "
             "?stage a efo:EFO_0000399 ; rdfs:label ?stageName . "
             "FILTER (?anat != obo:GO_0005575) "
             f"FILTER (LCASE(?geneName) = \"{literal}\") {_species_clause(species)}")
    return await _query("?geneName ?anat ?anatName ?stage ?stageName ?score", where, limit, offset)


@mcp.tool()
async def bgee_anatomy_genes(anatomy: str, species: str | None = None,
                             limit: int = 20, offset: int = 0) -> dict:
    """List genes expressed in one anatomical entity, matched by exact entity name."""
    literal = _name(anatomy, "anatomy")
    where = ("?gene a orth:Gene ; genex:isExpressedIn ?anat ; rdfs:label ?geneName ; "
             "orth:organism ?organism . "
             "?anat a genex:AnatomicalEntity ; rdfs:label ?anatName . "
             "?organism obo:RO_0002162 ?taxon . ?taxon a up:Taxon . "
             f"FILTER (LCASE(?anatName) = \"{literal}\") {_species_clause(species)}")
    return await _query("?geneName ?anat ?anatName", where, limit, offset)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
