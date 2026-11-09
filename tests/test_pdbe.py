from unittest.mock import AsyncMock, patch

import httpx

from servers.pdbe_mcp import server
from tests.helpers import HTTPTestCase


class PDBETests(HTTPTestCase):
    async def test_success_all_tools(self):
        paths = []

        def handler(req):
            paths.append(req.url.path)
            if "/summary/" in req.url.path:
                return httpx.Response(200, json={"1cbs": [{"title": "Retinoic acid", "experimental_method": ["X-ray diffraction"], "assemblies": [{"preferred": True}]}]})
            if "/uniprot/" in req.url.path:
                return httpx.Response(200, json={"1cbs": {"UniProt": {"P29373": {"identifier": "RABP2_HUMAN", "mappings": [{"chain_id": "A", "identity": 1.0, "coverage": 0.993}]}}}})
            if "/ena/" in req.url.path:
                return httpx.Response(200, json={"1cbs": {"ENA": {"AE000512": {"identifier": "genomic DNA", "mappings": [{"chain_id": "A"}]}}}})
            if "/all/" in req.url.path:
                return httpx.Response(200, json={"1cbs": {"UniProt": {"P29373": {}}, "Pfam": {"PF00061": {"name": "Lipocalin"}}}})
            if "/ligand_monomers/" in req.url.path:
                return httpx.Response(200, json={"1cbs": [{"chem_comp_id": "REA", "chem_comp_name": "RETINOIC ACID", "weight": 300.435}]})
            if "/modified_residues_or_NA/" in req.url.path:
                return httpx.Response(200, json={"1cbs": [{"parent_comp_id": "LYS", "details": "methylated"}]})
            if "/secondary_structure/" in req.url.path:
                return httpx.Response(200, json={"1cbs": {"molecules": [{"chains": [{"chain_id": "A", "secondary_structure": {"helices": [{"start": {"residue_number": 15}, "end": {"residue_number": 21}}], "strands": []}}]}]}})
            return httpx.Response(404)

        with self.mock_http(handler), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            summary = (await server.pdbe_entry_summary("1CBS"))["1cbs"][0]
            self.assertEqual(summary["experimental_method"], ["X-ray diffraction"])
            uniprot = (await server.pdbe_sifts_uniprot("1CBS"))["1cbs"]["UniProt"]["P29373"]
            self.assertEqual(uniprot["identifier"], "RABP2_HUMAN")
            ena = (await server.pdbe_sifts_ena("1CBS"))["1cbs"]["ENA"]
            self.assertIn("AE000512", ena)
            kb = (await server.pdbe_pdbe_kb_summary("1CBS"))["1cbs"]
            self.assertEqual(kb["Pfam"]["PF00061"]["name"], "Lipocalin")
            ligand = (await server.pdbe_ligands("1CBS"))["1cbs"][0]
            self.assertEqual(ligand["chem_comp_id"], "REA")
            modified = (await server.pdbe_modified_residues("1CBS"))["1cbs"][0]
            self.assertEqual(modified["parent_comp_id"], "LYS")
            helix = (await server.pdbe_secondary_structure("1CBS"))["1cbs"]["molecules"][0]["chains"][0]["secondary_structure"]["helices"][0]
            self.assertEqual(helix["end"]["residue_number"], 21)
        self.assertIn("/pdbe/api/pdb/entry/ligand_monomers/1cbs/", paths)

    async def test_validation_all_tools(self):
        for func in [server.pdbe_entry_summary, server.pdbe_sifts_uniprot, server.pdbe_sifts_ena,
                     server.pdbe_pdbe_kb_summary, server.pdbe_ligands, server.pdbe_modified_residues,
                     server.pdbe_secondary_structure]:
            with self.subTest(tool=func.__name__):
                with self.assertRaises(ValueError):
                    await func("bad")
                with self.assertRaises(ValueError):
                    await func("")

    async def test_api_error(self):
        with self.mock_http(lambda req: httpx.Response(404)), patch("common.http.asyncio.sleep", new_callable=AsyncMock):
            with self.assertRaises(httpx.HTTPStatusError):
                await server.pdbe_entry_summary("9999")
