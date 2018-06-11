# -*- coding: iso-8859-1 -*-
import string
import types
import logging
import unicodedata
from fiscalGeneric import PrinterInterface, PrinterException
import epsonFiscalDriver

class FiscalPrinterError(Exception):
    pass


class FileDriver:

    def __init__(self, filename):
        self.filename = filename
        self.file = open(filename, "w")

    def sendCommand(self, command, parameters):
        self.file.write("Command: %d, Parameters: %s\n" % (command, parameters))
        return ["BLA", "BLA", "BLA", "BLA", "BLA", "BLA", "BLA", "BLA", ]

    def close(self):
        self.file.close()


def formatText(text):
    asciiText = unicodedata.normalize('NFKD', unicode(text)).encode('ASCII', 'ignore')
    asciiText = asciiText.replace("\t", " ").replace("\n", " ").replace("\r", " ")
    return asciiText


class DummyDriver:

    def __init__(self):
        try:
            self.number = int(raw_input("Ingrese el n�mero de la �ltima factura: "))
        except EOFError:
            # iniciar desde 0 (ejecutando sin stdin)
            self.number = 0

    def close(self):
        pass

    def sendCommand(self, commandNumber, parameters, skipStatusErrors):
        ##raise RuntimeError("saraza1")
##        if commandNumber in EpsonPrinter.CMD_CLOSE_FISCAL_RECEIPT:
##            #raise RuntimeError("saraza")
##        else:
##            pass
        return ["00", "00", "", "", str(self.number), "", str(self.number)] + [str(self.number)] * 11


class EpsonPrinter(PrinterInterface):
    DEBUG = True

    CMD_OPEN_FISCAL_RECEIPT = 0x40
    CMD_OPEN_BILL_TICKET = 0x60
##    CMD_PRINT_TEXT_IN_FISCAL = (0x41, 0x61)
    CMD_PRINT_TEXT_IN_FISCAL = 0x41
    CMD_PRINT_LINE_ITEM = (0x42, 0x62)
    CMD_PRINT_SUBTOTAL = (0x43, 0x63)
    CMD_ADD_PAYMENT = (0x44, 0x64)
    CMD_CLOSE_FISCAL_RECEIPT = (0x45, 0x65)
    CMD_DAILY_CLOSE = 0x39
    CMD_STATUS_REQUEST = 0x2a

    CMD_OPEN_DRAWER = 0x7b

    CMD_SET_HEADER_TRAILER = 0x5d

    CMD_OPEN_NON_FISCAL_RECEIPT = 0x48
    CMD_PRINT_NON_FISCAL_TEXT = 0x49
    CMD_CLOSE_NON_FISCAL_RECEIPT = 0x4a

    CURRENT_DOC_TICKET = 1
    CURRENT_DOC_BILL_TICKET = 2
    CURRENT_DOC_CREDIT_TICKET = 4
    CURRENT_DOC_NON_FISCAL = 3

    models = ["tickeadoras", "epsonlx300+", "tm-220-af"]

    def __init__(self, deviceFile=None, speed=9600, host=None, port=None, dummy=False, model=None):
        try:
            if dummy:
                self.driver = DummyDriver()
            elif host:
                self.driver = epsonFiscalDriver.EpsonFiscalDriverProxy(host, port)
            else:
                deviceFile = deviceFile or 0
                self.driver = epsonFiscalDriver.EpsonFiscalDriver(deviceFile, speed)
            #self.driver = FileDriver( "/home/gnarvaja/Desktop/fiscal.txt" )
        except Exception, e:
            raise FiscalPrinterError("Imposible establecer comunicaci�n.", e)
        if not model:
            self.model = "tickeadoras"
        else:
            self.model = model
        self._currentDocument = None
        self._currentDocumentType = None

    def _sendCommand(self, commandNumber, parameters, skipStatusErrors=False):
        print "_sendCommand", commandNumber, parameters
        try:
            """
            logging.getLogger().info("sendCommand: SEND|0x%x|%s|%s" % (commandNumber,
                skipStatusErrors and "T" or "F",
                                                                     str(parameters)))
            """
            return self.driver.sendCommand(commandNumber, parameters, skipStatusErrors)
        except epsonFiscalDriver.PrinterException, e:
            logging.getLogger().error("epsonFiscalDriver.PrinterException: %s" % str(e))
            raise PrinterException("Error de la impresora fiscal: " + str(e))

    def openNonFiscalReceipt(self):
        status = self._sendCommand(self.CMD_OPEN_NON_FISCAL_RECEIPT, [])
        self._currentDocument = self.CURRENT_DOC_NON_FISCAL
        self._currentDocumentType = None
        return status

    def printNonFiscalText(self, text):
        return self._sendCommand(self.CMD_PRINT_NON_FISCAL_TEXT, [formatText(text[:40] or " ")])

    ivaTypeMap = {
        PrinterInterface.IVA_TYPE_RESPONSABLE_INSCRIPTO: 'I',
        PrinterInterface.IVA_TYPE_RESPONSABLE_NO_INSCRIPTO: 'R',
        PrinterInterface.IVA_TYPE_EXENTO: 'E',
        PrinterInterface.IVA_TYPE_NO_RESPONSABLE: 'N',
        PrinterInterface.IVA_TYPE_CONSUMIDOR_FINAL: 'F',
        PrinterInterface.IVA_TYPE_RESPONSABLE_NO_INSCRIPTO_BIENES_DE_USO: 'R',
        PrinterInterface.IVA_TYPE_RESPONSABLE_MONOTRIBUTO: 'M',
        PrinterInterface.IVA_TYPE_MONOTRIBUTISTA_SOCIAL: 'M',
        PrinterInterface.IVA_TYPE_PEQUENIO_CONTRIBUYENTE_EVENTUAL: 'F',
        PrinterInterface.IVA_TYPE_PEQUENIO_CONTRIBUYENTE_EVENTUAL_SOCIAL: 'F',
        PrinterInterface.IVA_TYPE_NO_CATEGORIZADO: 'F',
    }

    ADDRESS_SIZE = 30

    def _setHeaderTrailer(self, line, text):
        self._sendCommand(self.CMD_SET_HEADER_TRAILER, (str(line), text))

    def setHeader(self, header=None):
        "Establecer encabezados"
        if not header:
            header = []
        line = 3
        for text in (header + [chr(0x7f)]*3)[:3]: # Agrego chr(0x7f) (DEL) al final para limpiar las
                                                  # l�neas no utilizadas
            self._setHeaderTrailer(line, text)
            line += 1

    def setTrailer(self, trailer=None):
        "Establecer pie"
        if not trailer:
            trailer = []
        line = 11
        for text in (trailer + [chr(0x7f)] * 9)[:9]:
            self._setHeaderTrailer(line, text)
            line += 1

    def openBillCreditTicket(self, type, name, address, doc, docType, ivaType, reference="NC"):
        return self._openBillCreditTicket(type, name, address, doc, docType, ivaType, isCreditNote=True)

    def openBillTicket(self, type, name, address, doc, docType, ivaType):
        return self._openBillCreditTicket(type, name, address, doc, docType, ivaType, isCreditNote=False)

    def _openBillCreditTicket(self, type, name, address, doc, docType, ivaType, isCreditNote,
            reference=None):
        if not doc or filter(lambda x: x not in string.digits + "-.", doc or "") or not \
                docType in self.docTypeNames:
            doc, docType = "", ""
        else:
            doc = doc.replace("-", "").replace(".", "")
            docType = self.docTypeNames[docType]
        self._type = type
        if self.model == "epsonlx300+":
            parameters = [isCreditNote and "N" or "F", # Por ahora no soporto ND, que ser�a "D"
                "C",
                type, # Tipo de FC (A/B/C)
                "1",   # Copias - Ignorado
                "P",   # "P" la impresora imprime la lineas(hoja en blanco) o "F" preimpreso
                "17",   # Tama�o Carac - Ignorado
                "I",   # Responsabilidad en el modo entrenamiento - Ignorado
                self.ivaTypeMap.get(ivaType, "F"),   # Iva Comprador
                formatText(name[:40]), # Nombre
                formatText(name[40:80]), # Segunda parte del nombre - Ignorado
                formatText(docType) or (isCreditNote and "-" or ""),
                 # Tipo de Doc. - Si es NC obligado pongo algo
                doc or (isCreditNote and "-" or ""), # Nro Doc - Si es NC obligado pongo algo
                "N", # No imprime leyenda de BIENES DE USO
                formatText(address[:self.ADDRESS_SIZE] or "-"), # Domicilio
                formatText(address[self.ADDRESS_SIZE:self.ADDRESS_SIZE * 2]), # Domicilio 2da linea
                formatText(address[self.ADDRESS_SIZE * 2:self.ADDRESS_SIZE * 3]), # Domicilio 3ra linea
                (isCreditNote or self.ivaTypeMap.get(ivaType, "F") != "F") and "-" or "",
                # Remito primera linea - Es obligatorio si el cliente no es consumidor final
                "", # Remito segunda linea
                "C", # No somos una farmacia
                ]
        else:
            parameters = [isCreditNote and "M" or "T", # Ticket NC o Factura
                "C",  # Tipo de Salida - Ignorado
                type, # Tipo de FC (A/B/C)
                "1",   # Copias - Ignorado
                "P",   # Tipo de Hoja - Ignorado
                "17",   # Tama�o Carac - Ignorado
                "E",   # Responsabilidad en el modo entrenamiento - Ignorado
                self.ivaTypeMap.get(ivaType, "F"),   # Iva Comprador
                formatText(name[:40]), # Nombre
                formatText(name[40:80]), # Segunda parte del nombre - Ignorado
                formatText(docType) or (isCreditNote and "-" or ""),
                 # Tipo de Doc. - Si es NC obligado pongo algo
                doc or (isCreditNote and "-" or ""), # Nro Doc - Si es NC obligado pongo algo
                "N", # No imprime leyenda de BIENES DE USO
                formatText(address[:self.ADDRESS_SIZE] or "-"), # Domicilio
                formatText(address[self.ADDRESS_SIZE:self.ADDRESS_SIZE * 2]), # Domicilio 2da linea
                formatText(address[self.ADDRESS_SIZE * 2:self.ADDRESS_SIZE * 3]), # Domicilio 3ra linea
                (isCreditNote or self.ivaTypeMap.get(ivaType, "F") != "F") and "-" or "",
                # Remito primera linea - Es obligatorio si el cliente no es consumidor final
                "", # Remito segunda linea
                "C", # No somos una farmacia
                ]
        if isCreditNote:
            self._currentDocument = self.CURRENT_DOC_CREDIT_TICKET
        else:
            self._currentDocument = self.CURRENT_DOC_BILL_TICKET
        # guardo el tipo de FC (A/B/C)
        self._currentDocumentType = type
        return self._sendCommand(self.CMD_OPEN_BILL_TICKET, parameters)

    def _getCommandIndex(self):
        if self._currentDocument == self.CURRENT_DOC_TICKET:
            return 0
        elif self._currentDocument in (self.CURRENT_DOC_BILL_TICKET, self.CURRENT_DOC_CREDIT_TICKET):
            return 1
        elif self._currentDocument == self.CURRENT_DOC_NON_FISCAL:
            return 2
        raise "Invalid currentDocument"

    def openTicket(self, defaultLetter='B'):
        if self.model == "epsonlx300+":
            return self.openBillTicket(defaultLetter, "CONSUMIDOR FINAL", "", None, None,
                self.IVA_TYPE_CONSUMIDOR_FINAL)
        else:
            self._sendCommand(self.CMD_OPEN_FISCAL_RECEIPT, ["C"])
            self._currentDocument = self.CURRENT_DOC_TICKET

    def openDrawer(self):
        self._sendCommand(self.CMD_OPEN_DRAWER, [])

    def closeDocument(self):
        if self._currentDocument == self.CURRENT_DOC_TICKET:
            reply = self._sendCommand(self.CMD_CLOSE_FISCAL_RECEIPT[self._getCommandIndex()], ["T"])
            return reply[2]
        if self._currentDocument == self.CURRENT_DOC_BILL_TICKET:
            reply = self._sendCommand(self.CMD_CLOSE_FISCAL_RECEIPT[self._getCommandIndex()],
                [self.model == "epsonlx300+" and "F" or "T", self._type, "FINAL"])
            del self._type
            return reply[2]
        if self._currentDocument == self.CURRENT_DOC_CREDIT_TICKET:
            reply = self._sendCommand(self.CMD_CLOSE_FISCAL_RECEIPT[self._getCommandIndex()],
                [self.model == "epsonlx300+" and "N" or "M", self._type, "FINAL"])
            del self._type
            return reply[2]
        if self._currentDocument in (self.CURRENT_DOC_NON_FISCAL, ):
            return self._sendCommand(self.CMD_CLOSE_NON_FISCAL_RECEIPT, ["T"])
        raise NotImplementedError

    def cancelDocument(self):
        if self._currentDocument in (self.CURRENT_DOC_TICKET, self.CURRENT_DOC_BILL_TICKET,
                self.CURRENT_DOC_CREDIT_TICKET):
            status = self._sendCommand(self.CMD_ADD_PAYMENT[self._getCommandIndex()], ["Cancelar", "0", 'C'])
            return status
        if self._currentDocument in (self.CURRENT_DOC_NON_FISCAL, ):
            self.printNonFiscalText("CANCELADO")
            return self.closeDocument()
        raise NotImplementedError

    def addItem(self, description, quantity, price, iva, discount, discountDescription, negative=False):
        if type(description) in types.StringTypes:
            description = [description]
        if negative:
            sign = 'R'
        else:
            sign = 'M'
        quantityStr = str(int(quantity * 1000))
        if self.model == "epsonlx300+":
            bultosStr = str(int(quantity))
        else:
            bultosStr = "0" * 5  # No se usa en TM220AF ni TM300AF ni TMU220AF
        if self._currentDocumentType != 'A':
            # enviar con el iva incluido
            priceUnitStr = str(int(round(price * 100, 0)))
        else:
            if self.model == "tm-220-af":
                # enviar sin el iva (factura A)
                priceUnitStr =  "%0.4f" % (price / ((100.0 + iva) / 100.0))
            else:
                # enviar sin el iva (factura A)
                priceUnitStr = str(int(round((price / ((100 + iva) / 100)) * 100, 0)))
        ivaStr = str(int(iva * 100))
        extraparams = self._currentDocument in (self.CURRENT_DOC_BILL_TICKET,
            self.CURRENT_DOC_CREDIT_TICKET) and ["", "", ""] or []
        if self._getCommandIndex() == 0:
            for d in description[:-1]:
                self._sendCommand(self.CMD_PRINT_TEXT_IN_FISCAL,
                                   [formatText(d)[:20]])
        reply = self._sendCommand(self.CMD_PRINT_LINE_ITEM[self._getCommandIndex()],
                          [formatText(description[-1][:20]),
                            quantityStr, priceUnitStr, ivaStr, sign, bultosStr, "0" * 8] + extraparams)
        if discount:
            discountStr = str(int(discount * 100))
            self._sendCommand(self.CMD_PRINT_LINE_ITEM[self._getCommandIndex()],
                [formatText(discountDescription[:20]), "1000",
                  discountStr, ivaStr, 'R', "0", "0"] + extraparams)
        return reply

    def addPayment(self, description, payment):
        paymentStr = str(int(payment * 100))
        status = self._sendCommand(self.CMD_ADD_PAYMENT[self._getCommandIndex()],
                                   [formatText(description)[:20], paymentStr, 'T'])
        return status

    def addAdditional(self, description, amount, iva, negative=False):
        """Agrega un adicional a la FC.
            @param description  Descripci�n
            @param amount       Importe (sin iva en FC A, sino con IVA)
            @param iva          Porcentaje de Iva
            @param negative True->Descuento, False->Recargo"""
        if negative:
            sign = 'R'
        else:
            sign = 'M'
        quantityStr = "1000"
        bultosStr = "0"
        priceUnit = amount
        if self._currentDocumentType != 'A':
            # enviar con el iva incluido
            priceUnitStr = str(int(round(priceUnit * 100, 0)))
        else:
            # enviar sin el iva (factura A)
            priceUnitStr = str(int(round((priceUnit / ((100 + iva) / 100)) * 100, 0)))
        ivaStr = str(int(iva * 100))
        extraparams = self._currentDocument in (self.CURRENT_DOC_BILL_TICKET,
            self.CURRENT_DOC_CREDIT_TICKET) and ["", "", ""] or []
        reply = self._sendCommand(self.CMD_PRINT_LINE_ITEM[self._getCommandIndex()],
                          [formatText(description[:20]),
                            quantityStr, priceUnitStr, ivaStr, sign, bultosStr, "0"] + extraparams)
        return reply

    def subtotal(self, print_text=True, display=False, text="Subtotal"):
        if self._currentDocument in (self.CURRENT_DOC_TICKET, self.CURRENT_DOC_BILL_TICKET,
                self.CURRENT_DOC_CREDIT_TICKET):
            status = self._sendCommand(self.CMD_PRINT_SUBTOTAL[self._getCommandIndex()], ["P" if print_text else "O", text])
            return status
        raise NotImplementedError

    def dailyClose(self, type):
        reply = self._sendCommand(self.CMD_DAILY_CLOSE, [type, "P"])
        return reply[2:]

    def getLastNumber(self, letter):
        reply = self._sendCommand(self.CMD_STATUS_REQUEST, ["A"], True)
        if len(reply) < 3:
# La respuesta no es v�lida. Vuelvo a hacer el pedido y si hay alg�n error que se reporte como excepci�n
            reply = self._sendCommand(self.CMD_STATUS_REQUEST, ["A"], False)
        if letter == "A":
            return int(reply[6])
        else:
            return int(reply[4])

    def getLastCreditNoteNumber(self, letter):
        reply = self._sendCommand(self.CMD_STATUS_REQUEST, ["A"], True)
        if len(reply) < 3:
# La respuesta no es v�lida. Vuelvo a hacer el pedido y si hay alg�n error que se reporte como excepci�n
            reply = self._sendCommand(self.CMD_STATUS_REQUEST, ["A"], False)
        if letter == "A":
            return int(reply[10])
        else:
            return int(reply[11])

    def cancelAnyDocument(self):
        try:
            self._sendCommand(self.CMD_ADD_PAYMENT[0], ["Cancelar", "0", 'C'])
            return True
        except:
            pass
        try:
            self._sendCommand(self.CMD_ADD_PAYMENT[1], ["Cancelar", "0", 'C'])
            return True
        except:
            pass
        try:
            self._sendCommand(self.CMD_CLOSE_NON_FISCAL_RECEIPT, ["T"])
            return True
        except:
            pass
        return False

    def getWarnings(self):
        ret = []
        reply = self._sendCommand(self.CMD_STATUS_REQUEST, ["N"], True)
        printerStatus = reply[0]
        x = int(printerStatus, 16)
        if ((1 << 4) & x) == (1 << 4):
            ret.append("Poco papel para la cinta de auditor�a")
        if ((1 << 5) & x) == (1 << 5):
            ret.append("Poco papel para comprobantes o tickets")
        return ret

    def __del__(self):
        try:
            self.close()
        except:
            pass

    def close(self):
        self.driver.close()
        self.driver = None
        

class EpsonExtPrinter(EpsonPrinter):
    "Protocolo Extendido. Segunda Generaci�n. Nueva Tecnolog�a RG 3561/13 AFIP"

    DEBUG = True

    # EPSON Fiscal Segunada Generaci�n: comandos de dos bytes + extensi�n de dos bytes

    # Comandos comprobantes: Tique CF, Tique-Fact / Nota D�bito A B C M, Nota Cr�dito A B C M
    CMD_OPEN_FISCAL_RECEIPT = (0x0a01, 0x0b01, 0x0d01)
    CMD_PRINT_TEXT_IN_FISCAL = None
    CMD_PRINT_LINE_ITEM = (0x0a02, 0x0b02, 0x0d02)
    CMD_PRINT_SUBTOTAL = (0x0a03, 0x0b03, 0x0d03)
    CMD_ADD_PAYMENT = (0x0a05, 0x0b05, 0x0d05)
    CMD_INFO_TICKET = (0X0a0a, 0x0b0a, 0x0d0a)
    CMD_CLOSE_FISCAL_RECEIPT = (0x0a06, 0x0b06, 0x0d06)
    CMD_CANCEL_FISCAL_RECEIPT = (0x0a07, 0x0b07, 0x0d07)
    CMD_DAILY_CLOSE_Z = 0x0801
    CMD_DAILY_CLOSE_X = 0x0802
    CMD_PRINT_REPORT_X = 0x0805
    CMD_STATUS = 0x0001     # Informaci�n de status simple
    CMD_STATUS_REQUEST = 0x0830     # Informaci�n de acumuladores y contadores
    CMD_OPEN_DRAWER = 0x0707        # Abrir Caj�n de Dinero (cajon dinero 1)
    CMD_CUT_PAPER = 0x0702          # Cortar papel

    CMD_SET_HEADER_TRAILER = None

    CMD_OPEN_NON_FISCAL_RECEIPT = 0x0e01
    CMD_PRINT_NON_FISCAL_TEXT = 0x0e02
    CMD_CLOSE_NON_FISCAL_RECEIPT = 0x0e06

    CURRENT_DOC_TICKET = 1
    CURRENT_DOC_BILL_TICKET = 2
    CURRENT_DOC_CREDIT_TICKET = 4
    CURRENT_DOC_NON_FISCAL = 3

    docTypeMap = {
        PrinterInterface.DOC_TYPE_CUIT: "T",
        PrinterInterface.DOC_TYPE_CUIL: "L",
        PrinterInterface.DOC_TYPE_LIBRETA_ENROLAMIENTO: 'E',
        PrinterInterface.DOC_TYPE_LIBRETA_CIVICA: 'V',
        PrinterInterface.DOC_TYPE_DNI: 'D',
        PrinterInterface.DOC_TYPE_PASAPORTE: 'P',
    }

    ivaTypeMap = {
        PrinterInterface.IVA_TYPE_RESPONSABLE_INSCRIPTO: 'I',
        PrinterInterface.IVA_TYPE_RESPONSABLE_NO_INSCRIPTO: 'N',
        PrinterInterface.IVA_TYPE_EXENTO: 'E',
        PrinterInterface.IVA_TYPE_NO_RESPONSABLE: 'N',
        PrinterInterface.IVA_TYPE_CONSUMIDOR_FINAL: 'F',
        PrinterInterface.IVA_TYPE_RESPONSABLE_NO_INSCRIPTO_BIENES_DE_USO: 'R',
        PrinterInterface.IVA_TYPE_RESPONSABLE_MONOTRIBUTO: 'M',
        PrinterInterface.IVA_TYPE_MONOTRIBUTISTA_SOCIAL: 'T',
        PrinterInterface.IVA_TYPE_PEQUENIO_CONTRIBUYENTE_EVENTUAL: 'F',
        PrinterInterface.IVA_TYPE_PEQUENIO_CONTRIBUYENTE_EVENTUAL_SOCIAL: 'F',
        PrinterInterface.IVA_TYPE_NO_CATEGORIZADO: 'U',
    }

    paymentNames = {
        1: "Carta de credito documentario",
        2: "Cartas de credito simple",
        3: "Cheque",
        4: "Cheques cancelatorios",
        5: "Credito documentario",
        6: "Cuenta corriente",
        7: "Deposito",
        8: "Efectivo",
        9: "Endoso de cheque",
        10: "Factura de credito",
        11: "Garantias bancarias",
        12: "Giros",
        13: "Letras de cambio",
        14: "Medios de pago de comercio exterior",
        15: "Orden de pago documentaria",
        16: "Orden de pago simple",
        17: "Pago contra reembolso",
        18: "Remesa documentaria",
        19: "Remesa simple",
        20: "Tarjeta de credito",
        21: "Tarjeta de debito",
        22: "Ticket",
        23: "Transferencia bancaria",
        24: "Transferencia no bancaria",
        99: "Otros medios de pago",
    }
    paymentMap = dict([(v.upper(), k) for (k, v) in paymentNames.items()])

    models = ["TM-T900FA"]
    
    # Compatibilidad hacia atr�s: asociaci�n de letra a tipo de documento:
    LETTER_TICKET_MAP = {'': 83, 'A': 81, 'B': 82, 'C': 111, 'M': 118}
    LETTER_CREDIT_MAP = {'': 110, 'A': 112, 'B': 113, 'C': 114, 'M': 119}

    def __init__(self, deviceFile=None, speed=9600, host=None, port=None, dummy=False, model=None):
        try:
            if dummy:
                self.driver = DummyDriver()
            elif host:
                self.driver = epsonFiscalDriver.EpsonFiscalDriverProxy(host, port)
            else:
                deviceFile = deviceFile or 0
                self.driver = epsonFiscalDriver.EpsonExtFiscalDriver(deviceFile, speed)
        except Exception, e:
            raise FiscalPrinterError("Imposible establecer comunicaci�n.", e)
        if not model:
            self.model = "TM-T900FA"
        else:
            self.model = model.upper()
        self._currentDocument = None
        self._currentDocumentType = None

    def getWarnings(self):
        # estado = OK, WARNING, ERROR
        ret = {'estado':'OK', 'ERROR':'', 'WARNING':''}
        reply = self._sendCommand(self.CMD_STATUS_REQUEST, ['\0\0'], False)
        print 'getStatus reply=',reply
        
        """
        TODO:
        mascara = (1 << 10 | 1 << 11)
        status = ( fiscalStatus & mascara ) >> 10
        print 'status=',status, mascara
        """
        
        fiscalStatus  = repr(reply[1]).replace('\\x','').replace("'",'') # \xc0\x80 a c080 viv
        binario = str(bin(int(fiscalStatus, 16))[2:].zfill(16)) #c080 a 1100000010000000 vivi
        print 'fiscalStatus=',fiscalStatus, binario
        if binario[-12]+binario[-11]=='01':
            ret['estado'] = 'WARNING'
            ret['WARNING'] = "Memoria fiscal casi llena. "
        if binario[-4:] not in ('0000','0010','0101','0111'): # binario[-4] == 1<<3 ?
            ret['estado'] = 'ERROR'
            ret['ERROR'] += "Documento abierto. "
        if binario[-12]+binario[-11]=='10':
            ret['estado'] = 'ERROR'
            ret['ERROR'] += "Memoria fiscal llena. "
        if binario[-12]+binario[-11]=='11':
            ret['estado'] = 'ERROR'
            ret['ERROR'] += "Memoria fiscal con desperfecto. "
    
        return ret

    def dailyClose(self, type):
        if type.upper() == "X":
            return self.dailyCloseX()
        elif type.upper() == "Z":
            return self.dailyCloseZ()

    def getLastNumber(self, letter=''):
        tipo_cbte = str(self.LETTER_TICKET_MAP[letter])
        reply = self._sendCommand(self.CMD_STATUS_REQUEST, ['\0\0', tipo_cbte])
        return int(reply[10])

    def openDrawer(self):
        reply = self._sendCommand(self.CMD_OPEN_DRAWER, ['\0\0'])
        print reply

    def cutPaper(self):
        reply = self._sendCommand(self.CMD_CUT_PAPER, ['\0\0'])
        print reply

    def getLastCreditNoteNumber(self, letter):
        tipo_cbte = str(self.LETTER_CREDIT_MAP[letter])
        reply = self._sendCommand(self.CMD_STATUS_REQUEST, ['\0\0', tipo_cbte])
        return int(reply[10])

    def cancelAnyDocument(self):
        try:
            for i in range(3):
                self._sendCommand(self.CMD_CANCEL_FISCAL_RECEIPT[i], ["\0\0", ])
            return True
        except:
            pass
        try:
            reply = self._sendCommand(self.CMD_CLOSE_NON_FISCAL_RECEIPT, ['\0\1','','','','','','']) #['\0\1'] > Corta papel | ['\0\0'] > No corta
            return True
        except:
            pass
        return False

    def cancelDocument(self):
        if self._currentDocument in (self.CURRENT_DOC_TICKET, self.CURRENT_DOC_BILL_TICKET,
                self.CURRENT_DOC_CREDIT_TICKET):
            status = self._sendCommand(self.CMD_CANCEL_FISCAL_RECEIPT[self._getCommandIndex()], ["\0\0", ])
            return status
        raise NotImplementedError

    ###### Jornada fiscal ----------------------------------------------

    def dailyCloseZ(self): # Cierre Z
        reply = self._sendCommand(self.CMD_DAILY_CLOSE_Z, ['\0\0']) 
        #return reply[0] # TODO: N�mero de Cierre Z
        return True

    def dailyCloseX(self): # Cierre X
        reply = self._sendCommand(self.CMD_DAILY_CLOSE_X, ['\0\0']) 
        #return reply[0] # TODO: N�mero de Cierre cajero
        return True

    def printReportX(self): # Imprime reporte X
        reply = self._sendCommand(self.CMD_PRINT_REPORT_X, ['\0\0']) 
        return True

    ###### Documento fiscal ----------------------------------------------
    #               - openTicket
    #               - addItem
    #               - ...
    #               - closeTicket

    def _getCommandIndex(self):
        if self._currentDocument == self.CURRENT_DOC_TICKET:
            return 0
        elif self._currentDocument == self.CURRENT_DOC_BILL_TICKET:
            return 1
        elif self._currentDocument == self.CURRENT_DOC_CREDIT_TICKET:
            return 2
        elif self._currentDocument == self.CURRENT_DOC_NON_FISCAL:
            return 3
        raise "Invalid currentDocument"

    def openBillTicket(self, type, name, address, doc, docType, ivaType, reference="", cbtes_asoc=None):
        return self._openBillTicket(type, name, address, doc, docType, ivaType, reference=reference, cbtes_asoc=cbtes_asoc)

    def openBillCreditTicket(self, type, name, address, doc, docType, ivaType, reference=None, cbtes_asoc=None):
        return self._openBillTicket(type, name, address, doc, docType, ivaType, isCreditNote=True, reference=reference, cbtes_asoc=cbtes_asoc)

    def openDebitNoteTicket(self, type, name, address, doc, docType, ivaType, reference=None, cbtes_asoc=None):
        return self._openBillTicket(type, name, address, doc, docType, ivaType, isDebitNote=True, reference=reference, cbtes_asoc=cbtes_asoc)

    def _openBillTicket(self, type, name, address, doc, docType, ivaType,
                        isCreditNote=False, isDebitNote=False,
                        reference="", cbtes_asoc=None):
        # valores por defecto
        if not cbtes_asoc:
            cbtes_asoc = ["903-00001-00000001"] + [""] * 2
        if not reference:
            reference = "000-00000-00000000"
        if not doc or filter(lambda x: x not in string.digits + "-.", doc or "") or not \
                docType in self.docTypeMap:
            doc, docType = "", ""
        else:
            doc = doc.replace("-", "").replace(".", "")
        # la letra de la factura la determina la impresora, igual lo guardamos:
        self._type = type
        parameters = [
            formatText(name[:40]), # Nombre
            formatText(name[40:80]), # Segunda parte del nombre
            formatText(address[:self.ADDRESS_SIZE] or "-"), # Domicilio
            formatText(address[self.ADDRESS_SIZE:self.ADDRESS_SIZE * 2]), # Domicilio 2da linea
            formatText(address[self.ADDRESS_SIZE * 2:self.ADDRESS_SIZE * 3]), # Domicilio 3ra linea
            self.docTypeMap.get(docType, ""), doc,
            self.ivaTypeMap.get(ivaType, ""),   # Iva Comprador
            cbtes_asoc[0], cbtes_asoc[1], cbtes_asoc[2], # Remito primer, segunda y tercera linea
            reference
            ]
        assert len(parameters) == 12
        # determinar comando seg�n tipo de comprobante:
        if isCreditNote:
            self._currentDocument = self.CURRENT_DOC_CREDIT_TICKET
            cmd_ext = '\0\0'
        else:
            self._currentDocument = self.CURRENT_DOC_BILL_TICKET
            if isDebitNote:
                cmd_ext = '\x20\x00'
            else:
                cmd_ext = '\0\0'
        cmd = self.CMD_OPEN_FISCAL_RECEIPT[self._getCommandIndex()]
        # guardo el tipo de FC (A/B/C)
        self._currentDocumentType = type
        return self._sendCommand(cmd, [cmd_ext] + parameters)

    def openTicket(self, defaultLetter=''):
        "Abrir un Tique a 'CONSUMIDOR FINAL' (gen�rico, sin letra)"
        self._currentDocument = self.CURRENT_DOC_TICKET
        cmd = self.CMD_OPEN_FISCAL_RECEIPT[self._getCommandIndex()]
        cmd_ext = '\0\0'
        return self._sendCommand(cmd, [cmd_ext]) 

    def addItem(self, description, quantity, price, iva=21, discount='', discountDescription='', negative=False):
        cmd = self.CMD_PRINT_LINE_ITEM[self._getCommandIndex()]
        options = '\0\0'
        iva = str(int(iva * 100)) # TODO: debe ser sero si el emisor no es R.I.
        quantityStr = str(int(quantity * 10000))
        priceStr = str(int(price * 10000))
        item = [options, '','','','',description, quantityStr, priceStr, iva]
        # capmos opcionales:
        item += [""] * 7
        # campos obligatorios:
        item[13] = "X"      # codigo interno
        item[14] = "0"      # codigo de unidad de medida (0: sin descripci�n)
        assert len(item) == 16
        return self._sendCommand(cmd, item) 

    def closeDocument(self):
        cmd = self.CMD_CLOSE_FISCAL_RECEIPT[self._getCommandIndex()]
        # 0x0001 Corta papel
        # 0x0002 Devuelve respuesta electronica.
        # 0x0004 Imprime "Su Vuelto" con atributos
        # 0x0010 Utiliza cuenta corriente en pago automatico
        if self._currentDocument != self.CURRENT_DOC_CREDIT_TICKET:
            cmd_ext = '\x00\x17'
        else:
            cmd_ext = '\x00\x03'
        # campos opcionales:
        fields = ['','','','','','']
        if cmd != 0x0b06:
            fields += ['']
        reply = self._sendCommand(cmd, [cmd_ext] + fields)
        # devolver letra y n�mero de comprobante creado:
        if self._getCommandIndex() == 0:
            ret = reply[5]
        else:
            ret = reply[6] + reply[5]
        return ret

    def addPayment(self, description, payment, code=None, qty=1, detail=""):
        # determinar el c�digo de la forma de pago:
        if not code:
            code = self.paymentMap.get(description.upper(), None)
            if code:
                detail = ""
            else:
                detail = description
                code = 99
            description = ""
        if not isinstance(payment, basestring):
            payment = str(int(payment * 1000))
        cmd = self.CMD_ADD_PAYMENT[self._getCommandIndex()]
        parameters = [formatText(description)[:20],
                      formatText(description)[20:], 
                      "" if not qty else str(qty), "", "", code,
                      payment]
        assert len(parameters) == 7
        status = self._sendCommand(cmd, ['\0\0'] + parameters)
        return status

    def infoTicket(self):
        cmd = self.CMD_INFO_TICKET[self._getCommandIndex()]
        info = self._sendCommand(cmd, ['\0\0'])
        return info

    ###### Documento no fiscal ----------------------------------------------
    
    def openNonFiscalReceipt(self, encabezado=False): #anterior no tiene variabe de entrada... compatibilidad?
        print_encabezado = ['\0\1','',''] if encabezado else ['\0\0','','']
        status = self._sendCommand(self.CMD_OPEN_NON_FISCAL_RECEIPT, print_encabezado)
        self._currentDocument = self.CURRENT_DOC_NON_FISCAL
        self._currentDocumentType = None
        return status

    def printNonFiscalText(self, text):
        return self._sendCommand(self.CMD_PRINT_NON_FISCAL_TEXT, ['\0\0',formatText(text[:40] or " ")])


