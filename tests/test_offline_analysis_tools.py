"""Image-only offline analysis canaries; host tests skip absent optional wheels."""

import importlib.util
import io
import struct
import unittest

from agent_ext.scapy_offline import summarize_pcap


def _one_packet_pcap():
    payload = b"GET / HTTP/1.0\r\n"
    ethernet = bytes.fromhex("00112233445566778899aabb0800")
    ipv4 = struct.pack(
        ">BBHHHBBH4s4s", 0x45, 0, 20 + 20 + len(payload), 0,
        0x4000, 64, 6, 0, bytes((192, 0, 2, 1)), bytes((198, 51, 100, 2)),
    )
    tcp = struct.pack(">HHIIHHHH", 1234, 80, 0, 0, 0x5018, 4096, 0, 0)
    packet = ethernet + ipv4 + tcp + payload
    return (
        struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1)
        + struct.pack("<IIII", 1, 0, len(packet), len(packet)) + packet
    )


class OfflineAnalysisToolTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("scapy"), "image-only Scapy wheel")
    def test_bounded_pcap_summary_without_interface_discovery(self):
        result = summarize_pcap(io.BytesIO(_one_packet_pcap()), max_packets=1)
        self.assertEqual(result["packet_count"], 1)
        self.assertFalse(result["truncated"])
        packet = result["packets"][0]
        self.assertEqual(packet["source"], "192.0.2.1")
        self.assertEqual(packet["destination"], "198.51.100.2")
        self.assertEqual(packet["transport"], "tcp")
        self.assertEqual(packet["payload_hex_preview"], b"GET / HTTP/1.0\r\n".hex())

    def test_pcap_bound_rejects_out_of_range(self):
        for maximum in (0, 257, True):
            with self.subTest(maximum=maximum), self.assertRaises(ValueError):
                summarize_pcap(io.BytesIO(b"not-pcap"), max_packets=maximum)

    @unittest.skipUnless(importlib.util.find_spec("pydicom"), "image-only pydicom wheel")
    def test_dicom_metadata_round_trip(self):
        from pydicom.dataset import Dataset, FileMetaDataset
        from pydicom.filebase import DicomBytesIO
        from pydicom.uid import ExplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

        data = Dataset()
        data.file_meta = FileMetaDataset()
        data.file_meta.TransferSyntaxUID = ExplicitVRLittleEndian
        data.file_meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
        data.file_meta.MediaStorageSOPInstanceUID = generate_uid()
        data.SOPClassUID = SecondaryCaptureImageStorage
        data.SOPInstanceUID = data.file_meta.MediaStorageSOPInstanceUID
        data.PatientName = "Synthetic"
        stream = DicomBytesIO()
        data.save_as(stream, enforce_file_format=True)
        stream.seek(0)
        from pydicom import dcmread
        self.assertEqual(str(dcmread(stream).PatientName), "Synthetic")

    @unittest.skipUnless(importlib.util.find_spec("PIL"), "image-only Pillow wheel")
    def test_image_pixels_round_trip(self):
        from PIL import Image

        image = Image.new("RGB", (2, 1))
        image.putpixel((0, 0), (17, 42, 99))
        stream = io.BytesIO()
        image.save(stream, format="PNG")
        stream.seek(0)
        with Image.open(stream) as decoded:
            self.assertEqual(decoded.getpixel((0, 0)), (17, 42, 99))

    @unittest.skipUnless(importlib.util.find_spec("pypdf"), "image-only pypdf wheel")
    def test_pdf_text_round_trip(self):
        from pypdf import PdfReader, PdfWriter

        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        stream = io.BytesIO()
        writer.write(stream)
        stream.seek(0)
        self.assertEqual(len(PdfReader(stream).pages), 1)

    @unittest.skipUnless(importlib.util.find_spec("z3"), "image-only Z3 wheel")
    def test_constraint_solver_canary(self):
        from z3 import Int, Solver, sat

        value = Int("value")
        solver = Solver()
        solver.add(value * 7 + 3 == 38)
        self.assertEqual(solver.check(), sat)
        self.assertEqual(solver.model()[value].as_long(), 5)

    @unittest.skipUnless(importlib.util.find_spec("lxml"), "image-only lxml wheel")
    def test_markup_parser_canary(self):
        from lxml import html

        root = html.fromstring('<div data-name="synthetic"><span>ok</span></div>')
        self.assertEqual(root.xpath("//div/@data-name"), ["synthetic"])
